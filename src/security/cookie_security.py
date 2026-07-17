from functools import wraps
import time
import threading
from datetime import datetime, timezone

from fastapi import HTTPException

from config.loader import COOKIE_DEFAULT_RATE_LIMIT
from src.api.config import PERM_LEVEL_MAP
from src.models.crud.system.auth_cookie_crud import get_auth_cookie_by_hash
from src.security.ratelimit import RateLimit
from src.security.tokens import decode_jwt_token, hash_token
from src.services.logging import log_message

_ratelimiters: dict[str, RateLimit] = {}
_last_seen_by_token: dict[str, float] = {}
_cache_lock = threading.Lock()


def _place_in_ratelimiters(token_hash: str, rate_limit: int) -> RateLimit:
    current_time = time.time()
    _ratelimiters[token_hash] = RateLimit(
        limit=rate_limit,
        key_hash=token_hash,
    )
    _last_seen_by_token[token_hash] = current_time
    return _ratelimiters[token_hash]


def cleanup_inactive_cookie_ratelimiters(max_inactive_seconds: int) -> int:
    """Remove cached cookie ratelimiters that have been inactive for too long."""
    now = time.time()
    removed = 0
    with _cache_lock:
        stale_hashes = [
            token_hash
            for token_hash, last_seen in _last_seen_by_token.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for token_hash in stale_hashes:
            _last_seen_by_token.pop(token_hash, None)
            if _ratelimiters.pop(token_hash, None) is not None:
                removed += 1
    return removed


async def _obtain_ratelimit(token_hash: str) -> RateLimit:
    with _cache_lock:
        existing = _ratelimiters.get(token_hash)
        if existing is not None:
            _last_seen_by_token[token_hash] = time.time()
            return existing

    configured_limit = COOKIE_DEFAULT_RATE_LIMIT

    with _cache_lock:
        existing = _ratelimiters.get(token_hash)
        if existing is not None:
            _last_seen_by_token[token_hash] = time.time()
            return existing
        return _place_in_ratelimiters(token_hash, configured_limit)


def cookie_authentication(permission_level: int = 0):
    """Decorator that validates a cookie JWT and enforces per-token rate limits."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            cookie_token = getattr(request, "cookie_token", "") or getattr(request, "token", "")
            if not cookie_token:
                raise HTTPException(status_code=401, detail="Missing cookie token.")

            token_payload = decode_jwt_token(cookie_token)
            if token_payload is None:
                raise HTTPException(status_code=401, detail="Invalid cookie token.")

            token_hash = hash_token(cookie_token)
            cookie_row = await get_auth_cookie_by_hash(token_hash)
            if cookie_row is None:
                raise HTTPException(status_code=401, detail="Cookie token is not registered.")
            if cookie_row.revoked:
                raise HTTPException(status_code=401, detail="Cookie token has been revoked.")
            if cookie_row.expires_at <= datetime.now(timezone.utc):
                raise HTTPException(status_code=401, detail="Cookie token has expired.")

            ratelimit = await _obtain_ratelimit(token_hash)
            effective_permission_level = int(token_payload.get("permission_level", 0))

            if effective_permission_level < permission_level:
                raise HTTPException(status_code=403, detail="Insufficient permissions.")

            allowed, status = ratelimit.is_allowed()
            if not allowed:
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Rate limit exceeded.", "retry_after": status},
                )

            request._cookie_data = {
                "subject": token_payload.get("sub", ""),
                "username": token_payload.get("username", ""),
                "permission_level": effective_permission_level,
                "permission_name": PERM_LEVEL_MAP.get(effective_permission_level, "UNKNOWN"),
                "token_hash": token_hash[:12],
                "rate_limit": ratelimit.limit,
                "requests_remaining": ratelimit.limit - ratelimit.requests,
                "seconds_since_last_request": ratelimit.how_long_ago(),
            }

            log_message(
                f"[DEBUG] [COOKIE SECURITY] Cookie auth accepted for user "
                f"{request._cookie_data['username']} with level {effective_permission_level}."
            )
            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
