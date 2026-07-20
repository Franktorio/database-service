# ~/src/security/password_security.py
# Decorator orchestrator for password validation and rate limiting.

import time
import threading
from fastapi import HTTPException

from config.loader import LOGIN_ATTEMPTS_LIMIT, LOGIN_TIME_WINDOW
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.models.crud.system.user_crud import get_user_by_username
from src.security.tokens import create_cookie_token
from src.security.ratelimit import RateLimit

from src.security.tokens import verify_password

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
    


async def authenticate_password(username: str, password: str, ip_address: str) -> bool:
    """Return True on success, otherwise raise HTTPException with persistent auth logging."""
    rate_limiter = await _obtain_ratelimit(username)
    allowed, status = rate_limiter.is_allowed()
    if not allowed:
        await safe_add_persistent_log(
            log_type="USER RATE LIMIT",
            log_level="WARNING",
            message=f"Password rate limit exceeded for username={username}. retry_after={status:.2f}s",
            ip_address=ip_address,
        )
        raise HTTPException(
            status_code=429,
            detail={"error": "Password rate limit exceeded.", "retry_after": status},
        )
    
    user = await get_user_by_username(username)
    if user is None:
        await safe_add_persistent_log(
            log_type="USER AUTH",
            log_level="WARNING",
            message=f"Password authentication failed: unknown username={username}",
            ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail="Invalid username or password.")
    
    result = verify_password(password, user.password_hash, salt=user.password_salt, iterations=user.hash_iterations)
    if not result:
        await safe_add_persistent_log(
            log_type="USER AUTH",
            log_level="WARNING",
            message=f"Password authentication failed: invalid password for username={username}",
            ip_address=ip_address,
        )
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    await safe_add_persistent_log(
        log_type="USER AUTH",
        log_level="INFO",
        message=f"Password authentication accepted for username={username}",
        ip_address=ip_address,
    )
    
    return user

async def auth_and_grant_token(username: str, password: str, ip_address: str, expiration: int | None = None) -> tuple[str, int | None]:
    """Authenticate a user by username and password, and return a JWT token on success."""
    user = await authenticate_password(username, password, ip_address)
    
    if not user:
        raise HTTPException(status_code=401, detail="Invalid username or password.")

    token = await create_cookie_token(
        username=user.username,
        role=user.role,
        expires_minutes=expiration or 10,
    )
    return token, expiration
    