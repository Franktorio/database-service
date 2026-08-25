# ~/src/security/password_security.py
# Decorator orchestrator for password validation and rate limiting.

from config.loader import LOGIN_ATTEMPTS_LIMIT, LOGIN_TIME_WINDOW, JWT_EXP_MINUTES
from src.api.errors import api_error
from src.services.system.logging import log_message_for_ip
from src.models.crud.cache_invalidation import password_identifier, user_identifier
from src.models.crud.system.user.user_crud import get_user_by_username
from src.models.crud.system.user.user_role_crud import get_roles_for_user
from src.security.tokens import create_cookie_token
from src.security.tokens import verify_password
from src.services.system.cache.permissionscache import (
    cache_permission_json,
    get_cached_permission_json,
)
from src.services.system.cache.ratelimitcache import (
    cache_rate_limit,
    process_cached_rate_limit,
)
from src.services.system.cache.redis.client import PermissionServiceUnavailable, RateLimitServiceUnavailable
from config.settings import MONITORING_SETTINGS

NOT_FOUND = MONITORING_SETTINGS.NOT_FOUND
INVALID_DATA = MONITORING_SETTINGS.INVALID_DATA
TOO_SOON = MONITORING_SETTINGS.TOO_SOON
DENIED = MONITORING_SETTINGS.DENIED
ALLOWED = MONITORING_SETTINGS.ALLOWED


async def _get_user_permission_from_redis(username: str) -> dict | None:
    cached = await get_cached_permission_json(user_identifier(username))
    if cached is not None:
        return cached
    return None

async def _get_user_permission_payload(username: str) -> dict:
    """Retrieves the permission payload for the given username, either from cache or database."""
    cached_payload = await _get_user_permission_from_redis(username)
    if cached_payload is not None:
        return cached_payload

    user = await get_user_by_username(username)
    if user is None:
        return {
            "username": username,
            "roles": [],
            "role": "",
            "login_rate_limit": LOGIN_ATTEMPTS_LIMIT,
        }

    roles = await get_roles_for_user(user.id)
    payload = {
        "username": user.username,
        "roles": roles,
        "role": roles[0] if roles else "",
        "login_rate_limit": user.login_rate_limit,
    }
    await cache_permission_json(user_identifier(username), payload)
    return payload


async def _enforce_password_ratelimit(username: str, configured_limit: int) -> tuple[bool, float]:
    identifier = password_identifier(username)
    result = await process_cached_rate_limit(identifier)
    if result in (NOT_FOUND, INVALID_DATA):
        await cache_rate_limit(
            identifier,
            limit=configured_limit,
            window=LOGIN_TIME_WINDOW,
        )
        result = await process_cached_rate_limit(identifier)

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
        log_message_for_ip(ip_address, "User permissions cache unavailable.", "PASSWORD SECURITY", level="ERROR")
        raise api_error(503, "Authorization cache unavailable.")
    except RateLimitServiceUnavailable:
        log_message_for_ip(ip_address, "Password rate limiter unavailable: Redis is not reachable.", "PASSWORD SECURITY", level="ERROR")
        raise api_error(503, "Rate limiter service unavailable.")

    if not allowed:
        log_message_for_ip(ip_address, f"Password rate limit exceeded for username={username}. retry_after={status:.2f}s", "PASSWORD SECURITY", level="WARNING")
        raise api_error(429, "Password rate limit exceeded.", status)

    user = await get_user_by_username(username)
    if user is None:
        log_message_for_ip(ip_address, f"Password authentication failed: unknown username={username}", "PASSWORD SECURITY", level="WARNING")
        raise api_error(401, "Invalid username or password.")

    result = await verify_password(password, user.password_hash, salt=user.password_salt, iterations=user.hash_iterations)
    if not result:
        log_message_for_ip(ip_address, f"Password authentication failed: invalid password for username={username}", "PASSWORD SECURITY", level="WARNING")
        raise api_error(401, "Invalid username or password.")

    log_message_for_ip(ip_address, f"Password authentication accepted for username={username}", "PASSWORD SECURITY", level="INFO")

    return user

async def auth_and_grant_token(username: str, password: str, ip_address: str, expiration: int | None = None) -> tuple[str, int | None]:
    """Authenticate a user by username and password, and return a JWT token on success."""
    user = await authenticate_password(username, password, ip_address)
    
    if not user:
        raise api_error(401, "Invalid username or password.")

    roles = await get_roles_for_user(user.id)
    token = await create_cookie_token(
        username=user.username,
        role=roles[0] if roles else "",
        expires_minutes=expiration or JWT_EXP_MINUTES,
    )
    return token, (expiration or JWT_EXP_MINUTES)
    