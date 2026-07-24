from functools import wraps

from fastapi import HTTPException

from config.loader import RATE_LIMIT_WINDOW_SECONDS
from src.api.config import PERM_LEVEL_MAP
from src.models.crud.system.api_key_crud import get_api_key
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.models.tables.system.api_key_table import ApiKey
from src.security.extract import extract_bearer_token, extract_client_ip, extract_request_from_call
from src.security.tokens import hash_token
from src.services.system.cache.permissionscache import (
    cache_permission_json,
    get_cached_permission_json,
    remove_cached_permission_json,
)
from src.services.system.cache.ratelimitcache import (
    ALLOWED,
    DENIED,
    INVALID_DATA,
    NOT_FOUND,
    TOO_SOON,
    place_in_redis,
    process_request,
    remove_from_redis,
)
from src.services.system.cache.redis.client import PermissionServiceUnavailable, RateLimitServiceUnavailable

def _ratelimit_identifier(key_hash: str) -> str:
    return f"api_key:{key_hash}"


def _permission_identifier(key_hash: str) -> str:
    return f"api_key:{key_hash}"


def _to_permission_payload(api_key: ApiKey) -> dict:
    return {
        "permission_level": api_key.permission_level,
        "rate_limit": api_key.rate_limit,
        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "email": api_key.email,
    }


async def refresh_ratelimiter(api_key: ApiKey) -> None:
    """Refresh Redis cache entries for an API key after write operations."""
    await place_in_redis(
        _ratelimit_identifier(api_key.key_hash),
        limit=api_key.rate_limit,
        window=RATE_LIMIT_WINDOW_SECONDS,
    )
    await cache_permission_json(_permission_identifier(api_key.key_hash), _to_permission_payload(api_key))


async def remove_ratelimiter(key_hash: str) -> None:
    """Invalidate Redis cache entries for an API key hash."""
    await remove_from_redis(_ratelimit_identifier(key_hash))
    await remove_cached_permission_json(_permission_identifier(key_hash))


async def _get_api_permission_payload(key_hash: str) -> dict | None:
    cached = await get_cached_permission_json(_permission_identifier(key_hash))
    if cached is not None:
        return cached

    api_key = await get_api_key(key_hash)
    if api_key is None:
        return None

    payload = _to_permission_payload(api_key)
    await cache_permission_json(_permission_identifier(key_hash), payload)
    return payload


async def _check_ratelimit(
    key_hash: str,
    rate_limit: int,
    window_seconds: int,
    too_soon_window_seconds: int | None,
) -> tuple[bool, float]:
    identifier = _ratelimit_identifier(key_hash)
    result = await process_request(identifier, too_soon_window_seconds)
    if result in (NOT_FOUND, INVALID_DATA):
        await place_in_redis(identifier, limit=rate_limit, window=window_seconds)
        result = await process_request(identifier, too_soon_window_seconds)

    if result == ALLOWED:
        return True, 0.0
    if result == TOO_SOON:
        return False, float(too_soon_window_seconds or 1)
    if result == DENIED:
        return False, 0.0

    raise RuntimeError(f"Unexpected result from rate limit check: {result}")


def api_authentication(permission_level: int, too_soon_window_seconds: int | None = None):
    """Decorator to validate API key and enforce Redis-backed authorization flow."""

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            request = extract_request_from_call(args, kwargs)
            ip_address = extract_client_ip(request)
            api_key = extract_bearer_token(request)
            if not api_key:
                await safe_add_persistent_log(
                    log_type="API AUTH",
                    log_level="WARNING",
                    message="API authentication failed: missing/invalid Authorization Bearer token",
                    ip_address=ip_address,
                )
                raise HTTPException(
                    status_code=401,
                    detail="Missing or invalid Authorization header. Expected: Bearer <api_key>",
                )

            key_hash = hash_token(api_key)
            fingerprint = key_hash[:12]

            try:
                permission_payload = await _get_api_permission_payload(key_hash)
                if permission_payload is None:
                    await safe_add_persistent_log(
                        log_type="API AUTH",
                        log_level="WARNING",
                        message=f"API key not registered. fingerprint={fingerprint}",
                        ip_address=ip_address,
                    )
                    raise HTTPException(status_code=403, detail="API key is not registered.")

                allowed, retry_after = await _check_ratelimit(
                    key_hash,
                    rate_limit=int(permission_payload.get("rate_limit", 1)),
                    window_seconds=int(permission_payload.get("window_seconds", RATE_LIMIT_WINDOW_SECONDS)),
                    too_soon_window_seconds=too_soon_window_seconds,
                )
                if not allowed:
                    await safe_add_persistent_log(
                        log_type="API RATE LIMIT",
                        log_level="WARNING",
                        message=f"API rate limit exceeded. fingerprint={fingerprint} retry_after={retry_after:.2f}s",
                        ip_address=ip_address,
                    )
                    raise HTTPException(
                        status_code=429,
                        detail={"error": "Rate limit exceeded.", "retry_after": retry_after},
                    )

                effective_level = int(permission_payload.get("permission_level", -1))
                if effective_level < permission_level:
                    await safe_add_persistent_log(
                        log_type="API AUTH",
                        log_level="WARNING",
                        message=(
                            "Insufficient API permissions. "
                            f"fingerprint={fingerprint} required={permission_level} found={effective_level}"
                        ),
                        ip_address=ip_address,
                    )
                    raise HTTPException(status_code=403, detail="Insufficient permissions.")

                api_data = {
                    "api_key_fingerprint": fingerprint,
                    "permission_level": effective_level,
                    "permission_name": PERM_LEVEL_MAP.get(effective_level, "UNKNOWN"),
                    "rate_limit": int(permission_payload.get("rate_limit", 0)),
                }
                if request is not None:
                    request.state.api_data = api_data
                    request._api_data = api_data
                return await func(*args, **kwargs)
            except (RateLimitServiceUnavailable, PermissionServiceUnavailable):
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="Redis-backed auth cache unavailable.",
                    ip_address=ip_address,
                )
                raise HTTPException(status_code=503, detail="Authorization cache unavailable.")

        return wrapper

    return decorator
    
