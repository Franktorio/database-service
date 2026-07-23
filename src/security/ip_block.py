# ~/src/security/ip_block.py
# All requests pass through this layer to check if the IP is blocked. If blocked, it raises an HTTPException.
# An IP is blocked if it sends unreasonable requests, such as too many failed login attempts or too many requests in a short time.
# Blocked IPs are not enforced permanently, but a configurable time period, similar to a rate limit.
# They do not persist across server restarts, but are stored in memory for the duration of the server's uptime.

import time
import threading
from functools import wraps
from fastapi import Request, HTTPException
import ipaddress

from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.ratelimit import RateLimit, RateLimitServiceUnavailable
from config.loader import (
    IP_BLOCKING_ENABLED,
    IP_BLOCKING_THRESHOLD,
    IP_BLOCKING_TIME_WINDOW,
    IP_BLOCKING_DURATION,
    TRUSTED_PROXIES,
)
from src.services.system.logging import log_message

_ip_requests: dict[str, RateLimit] = {}  # Maps IP addresses to a RateLimit object that tracks the number of requests and the time window.
_blocked_until_by_ip: dict[str, float] = {}
_last_seen_by_ip: dict[str, float] = {}
_ip_lock = threading.Lock()  # A lock to synchronize access to the _ip_requests dictionary.


def _validate_ip_address(ip_address: str) -> bool:
    """Validate the format of an IP address (IPv4 or IPv6)."""

    try:
        ipaddress.ip_address(ip_address)
        return True
    except ValueError:
        return False


def _get_client_ip(request: Request) -> str | None:
    peer_ip = request.client.host if request.client else None

    if peer_ip in TRUSTED_PROXIES:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            return forwarded_for.split(",")[0].strip()

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip.strip()
        
    if not _validate_ip_address(peer_ip):
        return None

    return peer_ip


def _extract_request_from_call(args: tuple, kwargs: dict) -> Request | None:
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    return None


def _get_or_create_ip_ratelimit(ip_address: str) -> RateLimit:
    now = time.time()
    existing = _ip_requests.get(ip_address)
    if existing is not None:
        _last_seen_by_ip[ip_address] = now
        return existing

    limiter = RateLimit(limit=IP_BLOCKING_THRESHOLD, key_hash=ip_address)
    limiter.per_sec_refill = IP_BLOCKING_THRESHOLD / max(1, IP_BLOCKING_TIME_WINDOW)
    _ip_requests[ip_address] = limiter
    _last_seen_by_ip[ip_address] = now
    return limiter


def cleanup_inactive_ip_blocks(max_inactive_seconds: int) -> int:
    """Remove stale IP ratelimiters and expired blocks from memory cache."""
    now = time.time()
    removed = 0

    with _ip_lock:
        stale_ips = [
            ip
            for ip, last_seen in _last_seen_by_ip.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for ip in stale_ips:
            _last_seen_by_ip.pop(ip, None)
            if _ip_requests.pop(ip, None) is not None:
                removed += 1
            _blocked_until_by_ip.pop(ip, None)

        expired_blocks = [
            ip
            for ip, blocked_until in _blocked_until_by_ip.items()
            if blocked_until <= now
        ]
        for ip in expired_blocks:
            _blocked_until_by_ip.pop(ip, None)

    return removed


def with_ip_block(func):
    """Decorator that temporarily blocks abusive IPs using ratelimit-style tracking."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        if not IP_BLOCKING_ENABLED:
            return await func(*args, **kwargs)

        request = _extract_request_from_call(args, kwargs)
        ip_address = _get_client_ip(request) if request is not None else None
        if not ip_address:
            return await func(*args, **kwargs)

        now = time.time()
        blocked_retry_after: float | None = None
        newly_blocked = False

        with _ip_lock:
            blocked_until = _blocked_until_by_ip.get(ip_address, 0.0)
            if blocked_until > now:
                blocked_retry_after = blocked_until - now
                limiter = None
            else:
                limiter = _get_or_create_ip_ratelimit(ip_address)
                _last_seen_by_ip[ip_address] = now

        if blocked_retry_after is None and limiter is not None:
            try:
                allowed, _ = await limiter.is_allowed()
            except RateLimitServiceUnavailable:
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="IP block limiter unavailable: Redis is not reachable.",
                    ip_address=ip_address,
                )
                raise HTTPException(status_code=503, detail="Rate limiter service unavailable.")

            if not allowed:
                with _ip_lock:
                    _blocked_until_by_ip[ip_address] = time.time() + IP_BLOCKING_DURATION
                newly_blocked = True
                blocked_retry_after = float(IP_BLOCKING_DURATION)

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

