
from fastapi import HTTPException, Depends, Request

from config.loader import RATE_LIMIT_WINDOW_SECONDS
from src.api.config import PERM_LEVEL_MAP
from src.api.models import APIRequestData
from src.services.system.logging import log_message_for_ip
from src.models.crud.cache_invalidation import api_key_identifier
from src.models.crud.system.api_key_crud import get_api_key
from src.models.tables.system.api_key_table import ApiKey
from src.security.extract import extract_bearer_token, extract_client_ip
from src.security.tokens import hash_token

from src.services.system.cache.permissionscache import (
    cache_permission_json,
    get_cached_permission_json,
)
from src.services.system.cache.ratelimitcache import (
    ALLOWED,
    DENIED,
    INVALID_DATA,
    NOT_FOUND,
    TOO_SOON,
    place_in_redis,
    process_request,
)
from src.services.system.cache.redis.client import PermissionServiceUnavailable, RateLimitServiceUnavailable

PRINT_PREFIX = "API AUTH"


def _to_permission_payload(api_key: ApiKey) -> dict:
    """Converts an ApiKey object to a dictionary payload for caching and validation."""
    return {
        "key_hash": api_key.key_hash,
        "permission_level": api_key.permission_level,
        "rate_limit": api_key.rate_limit,
        "window_seconds": RATE_LIMIT_WINDOW_SECONDS,
        "email": api_key.email,
    }
    
def _to_api_key_object(payload: dict) -> ApiKey:
    """Converts a dictionary payload back to an ApiKey object."""
    return ApiKey(
        key_hash=payload.get("key_hash", ""),
        permission_level=payload.get("permission_level", 0),
        rate_limit=payload.get("rate_limit", 1),
        email=payload.get("email", ""),
    )


def to_api_request_data(api_key: ApiKey) -> APIRequestData:
    """Converts a validated ApiKey into the request-scoped payload exposed to route handlers."""
    return APIRequestData(
        api_key_fingerprint=api_key.key_hash[:12],
        permission_level=api_key.permission_level,
        permission_name=PERM_LEVEL_MAP.get(api_key.permission_level, "Unknown"),
        rate_limit=api_key.rate_limit,
    )


async def _get_api_permission_payload(key_hash: str) -> dict | None:
    cached = await get_cached_permission_json(api_key_identifier(key_hash))
    if cached is not None:
        return cached

    api_key = await get_api_key(key_hash)
    if api_key is None:
        return None

    payload = _to_permission_payload(api_key)
    await cache_permission_json(api_key_identifier(key_hash), payload)
    return payload


async def _check_ratelimit(
    key_hash: str,
    rate_limit: int,
    window_seconds: int,
    too_soon_window_seconds: int | None,
) -> tuple[bool, float]:
    identifier = api_key_identifier(key_hash)
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


def get_key_hash_from_request(request: Request) -> str | None:
    """Extracts the API key from the request and returns its hashed value."""
    api_key = extract_bearer_token(request)
    if not api_key:
        return None
    return hash_token(api_key)


async def get_current_api_key(
    request: Request,
    key_hash: str | None = Depends(get_key_hash_from_request),
) -> ApiKey:
    """Dependency that resolves and validates the caller's API key (existence only; no rate/permission checks)."""
    ip_address = extract_client_ip(request)
    if not key_hash:
        log_message_for_ip(ip_address, "Missing or invalid Authorization header.", PRINT_PREFIX, level="WARNING")
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header. Expected: Bearer <api_key>",
        )

    try:
        permission_payload = await _get_api_permission_payload(key_hash)
    except PermissionServiceUnavailable:
        log_message_for_ip(ip_address, "Authorization cache unavailable: Redis is not reachable.", PRINT_PREFIX, level="ERROR")
        raise HTTPException(status_code=503, detail="Authorization cache unavailable.")

    if permission_payload is None:
        log_message_for_ip(ip_address, "API key is not registered.", PRINT_PREFIX, level="WARNING")
        raise HTTPException(status_code=403, detail="API key is not registered.")

    return _to_api_key_object(permission_payload)


def api_key_rate_limited_factory(too_soon_window_seconds: int | None = None):
    """Factory for a dependency that enforces the resolved API key's own rate limit."""

    async def api_key_rate_limited(
        request: Request,
        api_key: ApiKey = Depends(get_current_api_key),
    ) -> ApiKey:
        ip_address = extract_client_ip(request)
        try:
            allowed, retry_after = await _check_ratelimit(
                api_key.key_hash,
                rate_limit=api_key.rate_limit,
                window_seconds=RATE_LIMIT_WINDOW_SECONDS,
                too_soon_window_seconds=too_soon_window_seconds,  # use the value from the factory closure
            )
        except (RateLimitServiceUnavailable, PermissionServiceUnavailable):
            log_message_for_ip(ip_address, "Authorization cache unavailable: Redis is not reachable.", PRINT_PREFIX, level="ERROR")
            raise HTTPException(status_code=503, detail="Authorization cache unavailable.")

        if not allowed:
            log_message_for_ip(ip_address, f"Rate limit exceeded. Retry after {retry_after} seconds.", PRINT_PREFIX, level="WARNING")
            raise HTTPException(
                status_code=429,
                detail={"error": "Rate limit exceeded.", "retry_after": retry_after},
            )
        return api_key

    return api_key_rate_limited


def api_key_authorized_factory(permission_level: int, too_soon_window_seconds: int | None = None):
    """Factory to create a dependency that checks for the required permission level.

    Depends chain: get_current_api_key (exists?) -> api_key_rate_limited (own rate limit) -> this (permission level).
    On success, the resolved `APIRequestData` is stashed on `request.state.api_data` for handlers/logging that want it.
    """
    dependency = api_key_rate_limited_factory(too_soon_window_seconds)

    async def api_key_authorized(
        request: Request,
        api_key: ApiKey = Depends(dependency),
    ) -> ApiKey:
        if api_key.permission_level < permission_level:
            ip_address = extract_client_ip(request)
            log_message_for_ip(ip_address, "Insufficient permissions.", PRINT_PREFIX, level="WARNING")
            raise HTTPException(status_code=403, detail="Insufficient permissions.")
        request.state.api_data = to_api_request_data(api_key)
        return api_key

    return api_key_authorized