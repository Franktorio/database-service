# ~/src/security/api_security.py
# Decorator orchestrator for API key validation and rate limiting.

from functools import wraps
import time
import threading
from fastapi import HTTPException

from src.models.tables.system.api_key_table import ApiKey
from src.models.crud.system.api_key_crud import get_api_key
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.tokens import hash_token
from src.security.ratelimit import RateLimit
from src.api.models import RequestBase
from src.api.config import PERM_LEVEL_MAP
from src.services.logging import log_message

_ratelimiters: dict[str, RateLimit] = {}
_last_seen_by_key: dict[str, float] = {}
_cache_lock = threading.Lock()


def _key_fingerprint(api_key: str) -> str:
    """Return a short non-reversible key fingerprint for safe logs."""
    return hash_token(api_key)[:12]

def _place_in_ratelimiters(api_key: ApiKey) -> RateLimit:
    """Place the API key in the rate limiters dictionary and return its RateLimit instance."""
    api_hash = api_key.key_hash
    limit = api_key.rate_limit
    level = api_key.permission_level
    current_time = time.time()
    _ratelimiters[api_hash] = RateLimit(limit=limit, key_hash=api_hash, permission_level=level)
    _last_seen_by_key[api_hash] = current_time
    log_message(f"[DEBUG] [API VALIDATE] Placed API key {api_hash} in rate limiters with limit {api_key.rate_limit}.")
    return _ratelimiters[api_hash]

def cleanup_inactive_ratelimiters(max_inactive_seconds: int) -> int:
    """Remove cached ratelimiters that have been inactive longer than the given threshold."""
    now = time.time()
    removed = 0
    with _cache_lock:
        stale_hashes = [
            api_hash
            for api_hash, last_seen in _last_seen_by_key.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for api_hash in stale_hashes:
            _last_seen_by_key.pop(api_hash, None)
            if _ratelimiters.pop(api_hash, None) is not None:
                removed += 1

    if removed > 0:
        log_message(
            f"[DEBUG] [API VALIDATE] Cleaned {removed} inactive ratelimiter(s) "
            f"older than {max_inactive_seconds}s."
        )
    return removed

async def _obtain_ratelimit(api_key: str) -> RateLimit | None:
    """Store the API key in the rate limiters dictionary and return its RateLimit instance."""
    api_hash = hash_token(api_key)

    with _cache_lock:
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
        )
        log_message(
            f"[WARNING] [API VALIDATE] Unknown API key attempted access. "
            f"fingerprint={_key_fingerprint(api_key)}"
        )
        return None

    with _cache_lock:
        existing = _ratelimiters.get(api_hash)
        if existing is not None:
            _last_seen_by_key[api_hash] = time.time()
            return existing
        return _place_in_ratelimiters(database_entry)


def api_authentication(permission_level: int):
    """Decorator to validate API key and enforce rate limiting."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: RequestBase, *args, **kwargs):
            api_key = request.api_key
            fingerprint = _key_fingerprint(api_key)
            ratelimit = await _obtain_ratelimit(api_key)
            
            if ratelimit is None:
                await safe_add_persistent_log(
                    log_type="API AUTH",
                    log_level="WARNING",
                    message=f"API key not registered. fingerprint={fingerprint}",
                )
                log_message(
                    f"[WARNING] [API VALIDATE] API key not registered. "
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
                )
                log_message(
                    f"[WARNING] [API VALIDATE] Insufficient permissions for key "
                    f"fingerprint={fingerprint}. Required={permission_level}, Found={ratelimit.permission_level}."
                )
                raise HTTPException(status_code=403, detail="Insufficient permissions.")
            
            allowed, status = ratelimit.is_allowed()
            if not allowed:
                await safe_add_persistent_log(
                    log_type="API RATE LIMIT",
                    log_level="WARNING",
                    message=f"API rate limit exceeded. fingerprint={fingerprint} retry_after={status:.2f}s",
                )
                log_message(
                    f"[WARNING] [API VALIDATE] Rate limit exceeded for key "
                    f"fingerprint={fingerprint}. retry_after={status:.2f}s"
                )
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Rate limit exceeded.", "retry_after": status},
                )

            await safe_add_persistent_log(
                log_type="API AUTH",
                log_level="INFO",
                message=(
                    "API key authentication accepted. "
                    f"fingerprint={fingerprint} permission={ratelimit.permission_level}"
                ),
            )
            
            api_data = {
                'api_key_fingerprint': fingerprint,
                'permission_level': ratelimit.permission_level,
                'permission_name': PERM_LEVEL_MAP.get(ratelimit.permission_level, "UNKNOWN"),
                'rate_limit': ratelimit.limit,
                'requests_remaining': ratelimit.limit - ratelimit.requests,
                'seconds_since_last_request': ratelimit.how_long_ago()
            }
            
            request._api_data = api_data
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
    
