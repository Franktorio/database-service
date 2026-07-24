# ~/src/security/password_security.py
# Decorator orchestrator for password validation and rate limiting.

from fastapi import HTTPException

from config.loader import LOGIN_ATTEMPTS_LIMIT, LOGIN_TIME_WINDOW
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.models.crud.system.user_crud import get_user_by_username
from src.security.tokens import create_cookie_token
from src.security.tokens import verify_password
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


def _password_ratelimit_identifier(username: str) -> str:
    return f"password:{username}"


def _user_permission_identifier(username: str) -> str:
    return f"user:{username}"


async def _get_user_permission_payload(username: str) -> dict:
    cached = await get_cached_permission_json(_user_permission_identifier(username))
    if cached is not None:
        return cached

    user = await get_user_by_username(username)
    if user is None:
        return {
            "username": username,
            "roles": [],
            "role": "",
            "login_rate_limit": LOGIN_ATTEMPTS_LIMIT,
        }

    payload = {
        "username": user.username,
        "roles": user.roles,
        "role": user.role,
        "login_rate_limit": user.login_rate_limit,
    }
    await cache_permission_json(_user_permission_identifier(username), payload)
    return payload


async def _enforce_password_ratelimit(username: str, configured_limit: int) -> tuple[bool, float]:
    identifier = _password_ratelimit_identifier(username)
    result = await process_request(identifier)
    if result in (NOT_FOUND, INVALID_DATA):
        await place_in_redis(
            identifier,
            limit=configured_limit,
            window=LOGIN_TIME_WINDOW,
        )
        result = await process_request(identifier)

    if result == ALLOWED:
        return True, 0.0
    if result in (DENIED, TOO_SOON):
        return False, 0.0
    raise RuntimeError(f"Unexpected password ratelimit result: {result}")
    


async def authenticate_password(username: str, password: str, ip_address: str) -> bool:
    """Return True on success, otherwise raise HTTPException with persistent auth logging."""

    try:
        permission_payload = await _get_user_permission_payload(username)
        configured_limit = int(permission_payload.get("login_rate_limit", LOGIN_ATTEMPTS_LIMIT))
        allowed, status = await _enforce_password_ratelimit(username, configured_limit)
    except PermissionServiceUnavailable:
        await safe_add_persistent_log(
            log_type="SERVICE",
            log_level="ERROR",
            message="Password permission cache unavailable: Redis is not reachable.",
            ip_address=ip_address,
        )
        raise HTTPException(status_code=503, detail="Authorization cache unavailable.")
    except RateLimitServiceUnavailable:
        await safe_add_persistent_log(
            log_type="SERVICE",
            log_level="ERROR",
            message="Password rate limiter unavailable: Redis is not reachable.",
            ip_address=ip_address,
        )
        raise HTTPException(status_code=503, detail="Rate limiter service unavailable.")

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
    