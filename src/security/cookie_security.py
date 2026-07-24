from functools import wraps
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from config.loader import COOKIE_DEFAULT_RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
from src.api.config import COOKIE_JWT_INDEX
from src.models.crud.system.auth_cookie_crud import get_auth_cookie_by_hash
from src.models.crud.system.user_crud import get_user_by_username
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.extract import extract_client_ip, extract_cookie_value
from src.security.tokens import decode_jwt_token, hash_token
from src.services.system.logging import log_message
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


def _cookie_ratelimit_identifier(token_hash: str) -> str:
    return f"cookie:{token_hash}"


def _user_permission_identifier(username: str) -> str:
    return f"user:{username}"


async def _resolve_user_permissions(username: str) -> dict | None:
    cached = await get_cached_permission_json(_user_permission_identifier(username))
    if cached is not None:
        return cached

    user = await get_user_by_username(username)
    if user is None:
        return None

    payload = {
        "username": user.username,
        "roles": user.roles,
        "role": user.role,
        "login_rate_limit": user.login_rate_limit,
    }
    await cache_permission_json(_user_permission_identifier(username), payload)
    return payload


async def _ensure_cookie_ratelimit(token_hash: str) -> tuple[bool, float]:
    identifier = _cookie_ratelimit_identifier(token_hash)
    result = await process_request(identifier)
    if result in (NOT_FOUND, INVALID_DATA):
        await place_in_redis(
            identifier,
            limit=COOKIE_DEFAULT_RATE_LIMIT,
            window=RATE_LIMIT_WINDOW_SECONDS,
        )
        result = await process_request(identifier)

    if result == ALLOWED:
        return True, 0.0
    if result in (DENIED, TOO_SOON):
        return False, 0.0
    raise RuntimeError(f"Unexpected cookie ratelimit result: {result}")

def cookie_authentication(required_roles: set[str] | None = None, redirect_url: str | None = None):
    """Decorator that validates a cookie JWT, enforces optional role checks, and per-token rate limits."""
    normalized_roles = {role.lower() for role in (required_roles or set())}

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            client_ip = extract_client_ip(request)
            cookie_token = extract_cookie_value(request, COOKIE_JWT_INDEX)
            if not cookie_token:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message="Cookie authentication failed: missing cookie token",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Missing cookie token.")

            token_payload = decode_jwt_token(cookie_token)
            if token_payload is None:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message="Cookie authentication failed: invalid JWT payload",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Invalid cookie token.")

            username_claim = token_payload.get("username")
            if not isinstance(username_claim, str) or not username_claim.strip():
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message="Cookie authentication failed: missing username claim",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Invalid cookie token payload.")

            token_hash = hash_token(cookie_token)
            try:
                allowed, status = await _ensure_cookie_ratelimit(token_hash)
            except RateLimitServiceUnavailable:
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="Cookie rate limiter unavailable: Redis is not reachable.",
                    ip_address=client_ip,
                )
                raise HTTPException(status_code=503, detail="Rate limiter service unavailable.")

            if not allowed:
                await safe_add_persistent_log(
                    log_type="USER RATE LIMIT",
                    log_level="WARNING",
                    message=(
                        "Cookie rate limit exceeded "
                        f"username={username_claim} retry_after={status:.2f}s"
                    ),
                    ip_address=client_ip,
                )
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Rate limit exceeded.", "retry_after": status},
                )

            cookie_row = await get_auth_cookie_by_hash(token_hash)
            if cookie_row is None:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=f"Cookie authentication failed: unregistered token hash={token_hash[:12]}",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Cookie token is not registered.")
            if cookie_row.revoked:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=f"Cookie authentication failed: revoked token hash={token_hash[:12]}",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Cookie token has been revoked.")
            if cookie_row.expires_at <= datetime.now(timezone.utc):
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=f"Cookie authentication failed: expired token hash={token_hash[:12]}",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Cookie token has expired.")

            username = cookie_row.username
            if username != username_claim:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message="Cookie authentication failed: username claim mismatch.",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Invalid cookie token payload.")

            try:
                permissions = await _resolve_user_permissions(username)
            except PermissionServiceUnavailable:
                await safe_add_persistent_log(
                    log_type="SERVICE",
                    log_level="ERROR",
                    message="User permissions cache unavailable.",
                    ip_address=client_ip,
                )
                raise HTTPException(status_code=503, detail="Authorization cache unavailable.")

            if permissions is None:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=f"Cookie authentication failed: user not found username={username}",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="User no longer exists.")

            roles = permissions.get("roles") or []
            effective_role = str(permissions.get("role") or (roles[0] if roles else "")).lower()
            if normalized_roles and effective_role not in normalized_roles:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=(
                        "Cookie authentication failed: insufficient role "
                        f"username={username} required_roles={sorted(normalized_roles)} "
                        f"found_role={effective_role}"
                    ),
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=403, detail="Insufficient role.")

            request._cookie_data = {
                "username": username,
                "role": effective_role,
                "token_hash": token_hash[:12],
                "rate_limit": COOKIE_DEFAULT_RATE_LIMIT,
                "requests_remaining": 0,
                "seconds_since_last_request": 0.0,
            }

            log_message(
                f"[DEBUG] [COOKIE SECURITY] Cookie auth accepted for user "
                f"{request._cookie_data['username']} with role {effective_role}."
            )
            await safe_add_persistent_log(
                log_type="USER AUTH",
                log_level="INFO",
                message=(
                    "Cookie authentication accepted "
                    f"username={request._cookie_data['username']} role={effective_role}"
                ),
                ip_address=client_ip,
            )

            response = await func(request, *args, **kwargs)
            if not isinstance(response, Response):
                response = JSONResponse(content=response)
            return response

        return wrapper

    return decorator
