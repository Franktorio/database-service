# ~/src/security/ip_block.py
# All requests pass through this layer to check if the IP is blocked. If blocked, it raises an HTTPException.
# An IP is blocked if it sends unreasonable requests, such as too many failed login attempts or too many requests in a short time.
# Blocked IPs are not enforced permanently, but a configurable time period, similar to a rate limit.
# They do not persist across server restarts, but are stored in memory for the duration of the server's uptime.

import time
from functools import wraps

from config.loader import (
    IP_BLOCKING_DURATION,
    IP_BLOCKING_ENABLED,
    IP_BLOCKING_THRESHOLD,
    IP_BLOCKING_TIME_WINDOW,
    REDIS_IP_BLOCK_EX_SECONDS,
    TRUSTED_PROXIES,
)
from src.api.errors import api_error
from src.security.extract import extract_client_ip, extract_request_from_call
from src.models.crud.cache_invalidation import ip_block_identifier
from src.services.system.cache.ratelimitcache import (
    cache_rate_limit,
    process_cached_rate_limit
)
from src.services.system.cache.redis.client import RateLimitServiceUnavailable
from src.services.system.cache.redis.client import RedisClient
from src.services.system.logging import log_message_for_ip
from config.settings import MONITORING_SETTINGS

NOT_FOUND = MONITORING_SETTINGS.NOT_FOUND
INVALID_DATA = MONITORING_SETTINGS.INVALID_DATA
TOO_SOON = MONITORING_SETTINGS.TOO_SOON
DENIED = MONITORING_SETTINGS.DENIED
ALLOWED = MONITORING_SETTINGS.ALLOWED

PRINT_PREFIX = "IP BLOCK"


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

        blocked_until = await RedisClient.get(ip_block_identifier(ip_address))
        if blocked_until is not None:
            try:
                blocked_until_time = float(blocked_until)
                if blocked_until_time > now:
                    blocked_retry_after = blocked_until_time - now
            except ValueError:
                log_message_for_ip(ip_address, f"Invalid blocked_until value for IP {ip_address}: {blocked_until}", PRINT_PREFIX, level="WARNING")
                blocked_retry_after = float(IP_BLOCKING_DURATION)
                pass
            
        if blocked_retry_after is None:
            try:
                result = await process_cached_rate_limit(identifier=ip_block_identifier(ip_address))
                if result in (NOT_FOUND, INVALID_DATA):
                    await cache_rate_limit(
                        ip_block_identifier(ip_address),
                        limit=IP_BLOCKING_THRESHOLD,
                        window=IP_BLOCKING_TIME_WINDOW,
                    )
                    # Allow the request to proceed since this is the first time seeing this IP
                    return await func(*args, **kwargs)
            except RateLimitServiceUnavailable:
                log_message_for_ip(ip_address, "IP block rate limiter unavailable: Redis is not reachable.", PRINT_PREFIX, level="ERROR")
                raise api_error(503, "Rate limiter service unavailable.")

            if result in (DENIED, TOO_SOON):
                newly_blocked = True
                blocked_retry_after = float(IP_BLOCKING_DURATION)
                await RedisClient.set(
                    ip_block_identifier(ip_address),
                    f"{time.time() + IP_BLOCKING_DURATION}",
                    ex=REDIS_IP_BLOCK_EX_SECONDS,
                )
            elif result != ALLOWED:
                raise RuntimeError(f"Unexpected IP block ratelimit result: {result}")

        if blocked_retry_after is not None:
            if newly_blocked:
                log_message_for_ip(
                    ip_address,
                    f"IP blocked due to request burst. "
                    f"ip={ip_address} unblock_in={IP_BLOCKING_DURATION}s",
                    PRINT_PREFIX,
                    level="WARNING",
                )
            else:
                log_message_for_ip(
                    ip_address,
                    f"IP temporarily blocked. "
                    f"ip={ip_address} retry_after={blocked_retry_after:.2f}s",
                    PRINT_PREFIX,
                    level="WARNING",
                )
            raise api_error(429, "IP temporarily blocked.", blocked_retry_after)

        return await func(*args, **kwargs)

    return wrapper

