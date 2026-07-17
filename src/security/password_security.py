# ~/src/security/password_security.py
# Decorator orchestrator for password validation and rate limiting.

from functools import wraps
import time
import threading
from fastapi import HTTPException

from config.loader import LOGIN_ATTEMPTS_LIMIT, LOGIN_TIME_WINDOW
from src.models.crud.user_crud import get_user_by_username
from src.security.ratelimit import RateLimit
from src.services.logging import log_message

# Dictionary to track per-user password login attempt rate limiters.
_ratelimiters: dict[str, RateLimit] = {}
_last_seen_by_user: dict[str, float] = {}
_cache_lock = threading.Lock()


def _place_in_ratelimiters(username: str, rate_limit: int) -> RateLimit:
    current_time = time.time()
    _ratelimiters[username] = RateLimit(limit=rate_limit, key_hash=username)
    _last_seen_by_user[username] = current_time
    return _ratelimiters[username]


def cleanup_inactive_password_ratelimiters(max_inactive_seconds: int = LOGIN_TIME_WINDOW) -> int:
    """Remove cached password ratelimiters that have been inactive for too long."""
    now = time.time()
    removed = 0
    with _cache_lock:
        stale_users = [
            username
            for username, last_seen in _last_seen_by_user.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for username in stale_users:
            _last_seen_by_user.pop(username, None)
            if _ratelimiters.pop(username, None) is not None:
                removed += 1
    return removed


async def _obtain_ratelimit(username: str) -> RateLimit:
    with _cache_lock:
        existing = _ratelimiters.get(username)
        if existing is not None:
            _last_seen_by_user[username] = time.time()
            return existing

    user = await get_user_by_username(username)
    configured_limit = user.login_rate_limit if user is not None else LOGIN_ATTEMPTS_LIMIT

    with _cache_lock:
        existing = _ratelimiters.get(username)
        if existing is not None:
            _last_seen_by_user[username] = time.time()
            return existing
        return _place_in_ratelimiters(username, configured_limit)


def password_authentication():
    """Decorator that rate-limits password-auth attempts by username."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            username = getattr(request, "username", "")
            if not username:
                raise HTTPException(status_code=400, detail="Missing username for password authentication.")

            ratelimit = await _obtain_ratelimit(username)
            allowed, status = ratelimit.is_allowed()
            if not allowed:
                log_message(
                    f"[WARNING] [PASSWORD SECURITY] Password rate limit exceeded for user {username}. "
                    f"retry_after={status:.2f}s"
                )
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Password rate limit exceeded.", "retry_after": status},
                )

            return await func(request, *args, **kwargs)

        return wrapper

    return decorator
        