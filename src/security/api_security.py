# ~/src/security/api_security.py
# Decorator orchestrator for API key validation and rate limiting.

from functools import wraps
import asyncio
import time
from fastapi import HTTPException, Request

from src.models.tables.system.api_key_table import ApiKey
from src.models.crud.system.api_key_crud import get_api_key
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.tokens import hash_token
from src.security.ratelimit import RateLimit, RateLimitServiceUnavailable
from src.api.config import PERM_LEVEL_MAP
from src.services.system.logging import log_message
from src.services.system.cache.redis.client import RedisClient

_ratelimiters: dict[str, RateLimit] = {}
_last_seen_by_key: dict[str, float] = {}
_cache_lock = asyncio.Lock()

PRINT_PREFIX = "API VALIDATE"


def _client_ip(request: Request | None) -> str | None:
    if request is None:
        return None
    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host:
            return host
    return None


def _extract_request_from_call(args: tuple, kwargs: dict) -> Request | None:
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    return None


def _extract_bearer_api_key(request: Request | None) -> str | None:
    if request is None:
        return None

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None

    stripped = token.strip()
    return stripped or None


def _key_fingerprint(api_key: str) -> str:
    """Return a short non-reversible key fingerprint for safe logs."""
    return hash_token(api_key)[:12]

def _place_in_ratelimiters(api_key: ApiKey) -> RateLimit:
    """Place the API key in the rate limiters dictionary and return its RateLimit instance."""
    api_hash = api_key.key_hash
    limit = api_key.rate_limit
    level = api_key.permission_level
    current_time = time.time()
    _ratelimiters[api_hash] = RateLimit(
        limit=limit,
        key_hash=api_hash,
        permission_level=level,
    )
    _last_seen_by_key[api_hash] = current_time
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Placed API hash {api_hash[:12]}... in rate limiters with limit {api_key.rate_limit}.")
    return _ratelimiters[api_hash]

async def refresh_ratelimiter(api_object: ApiKey) -> RateLimit:
    """
    Refresh the RateLimit instance for the given API key in the ratelimiters dictionary. 
    Use when the API key's rate limit has changed in the database. 
    Does not check if the API key exists in the database; it assumes the caller has already verified that.
    """
    api_hash = api_object.key_hash
    limiter = _ratelimiters.get(api_hash)
    if limiter is not None:
        await limiter.delete() # Remove the old RateLimit instance from Redis
    async with _cache_lock:
        _ratelimiters[api_hash] = _place_in_ratelimiters(api_object)
        _last_seen_by_key[api_hash] = time.time()
    
    return _ratelimiters[api_hash]

async def remove_ratelimiter(api_hash: str) -> bool:
    """Remove the RateLimit instance for the given API key from the ratelimiters dictionary. Returns True if removed, False if not found."""
    limiter = _ratelimiters.get(api_hash)
    if limiter is not None:
        await limiter.delete()  # Remove the RateLimit instance from Redis
    async with _cache_lock:
        removed = _ratelimiters.pop(api_hash, None) is not None
        _last_seen_by_key.pop(api_hash, None)
    if removed:
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Removed API hash {api_hash[:12]}... from rate limiters.")
    else:
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Attempted to remove API hash {api_hash[:12]}... from rate limiters, but it was not found.")
    return removed

async def cleanup_inactive_ratelimiters(max_inactive_seconds: int) -> int:
    """Remove cached ratelimiters that have been inactive longer than the given threshold."""
    now = time.time()
    removed = 0
    stale_limiters: list[RateLimit] = []
    async with _cache_lock:
        stale_hashes = [
            api_hash
            for api_hash, last_seen in _last_seen_by_key.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for api_hash in stale_hashes:
            _last_seen_by_key.pop(api_hash, None)
            limiter = _ratelimiters.pop(api_hash, None)
            if limiter is not None:
                stale_limiters.append(limiter)
                removed += 1

    for limiter in stale_limiters:
        try:
            await limiter.delete()
        except RateLimitServiceUnavailable:
            log_message(
                f"[WARNING] [{PRINT_PREFIX}] Failed to delete stale limiter in Redis during cleanup."
            )

    if removed > 0:
        log_message(
            f"[DEBUG] [{PRINT_PREFIX}] Cleaned {removed} inactive ratelimiter(s) "
            f"older than {max_inactive_seconds}s."
        )
    return removed

async def _obtain_ratelimit(api_key: str, ip_address: str | None = None) -> RateLimit | None:
    """Store the API key in the rate limiters dictionary and return its RateLimit instance."""
    api_hash = hash_token(api_key)

    async with _cache_lock:
        existing = _ratelimiters.get(api_hash)
        if existing is not None:
            _last_seen_by_key[api_hash] = time.time()
            return existing
    
    database_entry = await get_api_key(api_hash)
    
    if database_entry is None:
        await safe_add_persistent_log(
            log_type="API AUTH",
            log_level="WARNING",
            message=(
                "Unknown API key attempted access. "
                f"fingerprint={_key_fingerprint(api_key)}"
            ),
            ip_address=ip_address,
        )
        log_message(
            f"[WARNING] [{PRINT_PREFIX}] Unknown API key attempted access. "
            f"fingerprint={_key_fingerprint(api_key)}"
        )
        return None

    async with _cache_lock:
        existing = _ratelimiters.get(api_hash)
        if existing is not None:
            _last_seen_by_key[api_hash] = time.time()
            return existing
        return _place_in_ratelimiters(database_entry)


def api_authentication(permission_level: int):
    """Decorator to validate API key and enforce rate limiting."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = _extract_request_from_call(args, kwargs)
            api_key = _extract_bearer_api_key(request)
            client_ip = _client_ip(request)

            if not api_key:
                await safe_add_persistent_log(
                    log_type="API AUTH",
                    log_level="WARNING",
                    message="API authentication failed: missing/invalid Authorization Bearer token",
                    ip_address=client_ip,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Missing or invalid Authorization header. Expected: Bearer <api_key>",
                )

            fingerprint = _key_fingerprint(api_key)
            ratelimit = await _obtain_ratelimit(api_key, ip_address=client_ip)
            
            if ratelimit is None:
                await safe_add_persistent_log(
                    log_type="API AUTH",
                    log_level="WARNING",
                    message=f"API key not registered. fingerprint={fingerprint}",
                    ip_address=client_ip,
                )
                log_message(
                    f"[WARNING] [{PRINT_PREFIX}] API key not registered. "
                    f"fingerprint={fingerprint}"
                )
                raise HTTPException(status_code=403, detail="API key is not registered.")
            
            if ratelimit.permission_level < permission_level:
                await safe_add_persistent_log(
                    log_type="API AUTH",
                    log_level="WARNING",
                    message=(
                        "Insufficient API permissions. "
                        f"fingerprint={fingerprint} required={permission_level} "
                        f"found={ratelimit.permission_level}"
                    ),
                    ip_address=client_ip,
                )
                log_message(
                    f"[WARNING] [{PRINT_PREFIX}] Insufficient permissions for key "
                    f"fingerprint={fingerprint}. Required={permission_level}, Found={ratelimit.permission_level}."
                )
                raise HTTPException(status_code=403, detail="Insufficient permissions.")
            
            try:
                allowed, status = await ratelimit.is_allowed()
            except RateLimitServiceUnavailable:
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="API rate limiter unavailable: Redis is not reachable.",
                    ip_address=client_ip,
                )
                raise HTTPException(
                    status_code=503,
                    detail="Rate limiter service unavailable.",
                )
            if not allowed:
                await safe_add_persistent_log(
                    log_type="API RATE LIMIT",
                    log_level="WARNING",
                    message=f"API rate limit exceeded. fingerprint={fingerprint} retry_after={status:.2f}s",
                    ip_address=client_ip,
                )
                log_message(
                    f"[WARNING] [{PRINT_PREFIX}] Rate limit exceeded for key "
                    f"fingerprint={fingerprint}. retry_after={status:.2f}s"
                )
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Rate limit exceeded.", "retry_after": status},
                )
            
            seconds_since_last_request = 0.0
            try:
                seconds_since_last_request = await ratelimit.how_long_ago()
            except RateLimitServiceUnavailable:
                # Keep request processing successful even if telemetry field is unavailable.
                seconds_since_last_request = 0.0

            api_data = {
                'api_key_fingerprint': fingerprint,
                'permission_level': ratelimit.permission_level,
                'permission_name': PERM_LEVEL_MAP.get(ratelimit.permission_level, "UNKNOWN"),
                'rate_limit': ratelimit.limit,
                'requests_remaining': int(status) if allowed else 0,
                'seconds_since_last_request': seconds_since_last_request,
            }

            if request is not None:
                request.state.api_data = api_data
                request._api_data = api_data
            
            return await func(*args, **kwargs)
        return wrapper
    return decorator
    
