# ~/src/security/ip_block.py
# All requests pass through this layer to check if the IP is blocked. If blocked, it raises an HTTPException.
# An IP is blocked if it sends unreasonable requests, such as too many failed login attempts or too many requests in a short time.
# Blocked IPs are not enforced permanently, but a configurable time period, similar to a rate limit.
# They do not persist across server restarts, but are stored in memory for the duration of the server's uptime.

import time
from functools import wraps
from fastapi import HTTPException

from config.loader import (
    IP_BLOCKING_DURATION,
    IP_BLOCKING_ENABLED,
    IP_BLOCKING_THRESHOLD,
    IP_BLOCKING_TIME_WINDOW,
    REDIS_IP_BLOCK_EX_SECONDS,
    TRUSTED_PROXIES,
)
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.extract import extract_client_ip, extract_request_from_call
from src.services.system.cache.ratelimitcache import (
    ALLOWED,
    DENIED,
    INVALID_DATA,
    NOT_FOUND,
    TOO_SOON,
    place_in_redis,
    process_request,
)
from src.services.system.cache.redis.client import RateLimitServiceUnavailable
from src.services.system.cache.redis.client import RedisClient
from src.services.system.logging import log_message


def _ip_ratelimit_identifier(ip_address: str) -> str:
    return f"ip_block:{ip_address}"

def with_ip_block(func):
    """Decorator that temporarily blocks abusive IPs using ratelimit-style tracking."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not IP_BLOCKING_ENABLED:
            return await func(*args, **kwargs)

        request = extract_request_from_call(args, kwargs)
        ip_address = extract_client_ip(request, TRUSTED_PROXIES)
        if not ip_address:
            return await func(*args, **kwargs)

        now = time.time()
        blocked_retry_after: float | None = None
        newly_blocked = False

        blocked_until = await RedisClient.get(f"ip_block:{ip_address}")
        if blocked_until is not None:
            try:
                blocked_until_time = float(blocked_until)
                if blocked_until_time > now:
                    blocked_retry_after = blocked_until_time - now
            except ValueError:
                log_message(f"[WARNING] [IP BLOCK] Invalid blocked_until value for IP {ip_address}: {blocked_until}")
                blocked_retry_after = float(IP_BLOCKING_DURATION)
                pass
            
        if blocked_retry_after is None:
            try:
                result = await process_request(_ip_ratelimit_identifier(ip_address))
                if result in (NOT_FOUND, INVALID_DATA):
                    await place_in_redis(
                        _ip_ratelimit_identifier(ip_address),
                        limit=IP_BLOCKING_THRESHOLD,
                        window=IP_BLOCKING_TIME_WINDOW,
                    )
                    result = await process_request(_ip_ratelimit_identifier(ip_address))
            except RateLimitServiceUnavailable:
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="IP block limiter unavailable: Redis is not reachable.",
                    ip_address=ip_address,
                )
                raise HTTPException(status_code=503, detail="Rate limiter service unavailable.")

            if result in (DENIED, TOO_SOON):
                newly_blocked = True
                blocked_retry_after = float(IP_BLOCKING_DURATION)
                await RedisClient.set(
                    f"ip_block:{ip_address}",
                    f"{time.time() + IP_BLOCKING_DURATION}",
                    ex=REDIS_IP_BLOCK_EX_SECONDS,
                )
            elif result != ALLOWED:
                raise RuntimeError(f"Unexpected IP block ratelimit result: {result}")

        if blocked_retry_after is not None:
            if newly_blocked:
                log_message(
                    f"[WARNING] [IP BLOCK] IP blocked due to request burst. "
                    f"ip={ip_address} unblock_in={IP_BLOCKING_DURATION}s"
                )
                await safe_add_persistent_log(
                    log_type="IP BLOCK",
                    log_level="WARNING",
                    message=(
                        "IP blocked due to request burst. "
                        f"unblock_in={IP_BLOCKING_DURATION}s"
                    ),
                    ip_address=ip_address,
                )
            else:
                await safe_add_persistent_log(
                    log_type="IP BLOCK",
                    log_level="WARNING",
                    message=(
                        "Blocked IP attempted request during active block. "
                        f"retry_after={blocked_retry_after:.2f}s"
                    ),
                    ip_address=ip_address,
                )

            raise HTTPException(
                status_code=429,
                detail={"error": "IP temporarily blocked.", "retry_after": blocked_retry_after},
            )

        return await func(*args, **kwargs)

    return wrapper

