from datetime import datetime, timezone

from fastapi import Depends, Request

from config.loader import COOKIE_DEFAULT_RATE_LIMIT, RATE_LIMIT_WINDOW_SECONDS
from src.api.config import COOKIE_JWT_INDEX
from src.api.errors import api_error
from src.api.models import CookieRequestData
from src.services.system.logging import log_message_for_ip
from src.models.crud.audit_context import set_audit_actor
from src.models.crud.cache_invalidation import cookie_identifier, user_identifier
from src.models.crud.system.auth_cookie_crud import get_auth_cookie_by_hash
from src.models.crud.system.user_crud import get_user_by_id, get_user_by_username
from src.security.extract import extract_client_ip, extract_cookie_value
from src.security.tokens import decode_jwt_token, hash_token

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

PRINT_PREFIX = "COOKIE SECURITY"



async def _resolve_user_permissions(username: str) -> dict | None:
    cached = await get_cached_permission_json(user_identifier(username))
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
    await cache_permission_json(user_identifier(username), payload)
    return payload


async def _resolve_cookie_row(token_hash: str):
    cached = await get_cached_permission_json(cookie_identifier(token_hash))
    if cached is not None:
        return cached

    cookie_row = await get_auth_cookie_by_hash(token_hash)
    if cookie_row is None:
        return None

    user = await get_user_by_id(cookie_row.user_id)
    if user is None:
        return None

    payload = {
        "username": user.username,
        "user_id": cookie_row.user_id,
        "revoked": cookie_row.revoked,
        "expires_at": cookie_row.expires_at.isoformat() if cookie_row.expires_at else None,
    }
    await cache_permission_json(cookie_identifier(token_hash), payload)
    return payload


async def _ensure_cookie_ratelimit(token_hash: str) -> tuple[bool, float]:
    identifier = cookie_identifier(token_hash)
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


def get_cookie_token_from_request(request: Request) -> str | None:
    """Extracts the raw JWT cookie value from the request."""
    return extract_cookie_value(request, COOKIE_JWT_INDEX)


async def get_cookie_claims(
    request: Request,
    cookie_token: str | None = Depends(get_cookie_token_from_request),
) -> dict:
    """Dependency that decodes and shape-validates the cookie JWT (no DB lookups yet)."""
    client_ip = extract_client_ip(request)
    if not cookie_token:
        log_message_for_ip(client_ip, "Missing cookie token.", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Missing cookie token.")

    token_payload = decode_jwt_token(cookie_token)
    if token_payload is None:
        log_message_for_ip(client_ip, "Cookie authentication failed: invalid JWT payload", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Invalid cookie token.")

    username_claim = token_payload.get("username")
    if not isinstance(username_claim, str) or not username_claim.strip():
        log_message_for_ip(client_ip, "Cookie authentication failed: missing username claim", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Invalid cookie token payload.")

    user_id_claim = token_payload.get("user_id")
    if user_id_claim is not None and not isinstance(user_id_claim, int):
        log_message_for_ip(client_ip, "Cookie authentication failed: invalid user_id claim", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Invalid cookie token payload.")

    return {
        "username": username_claim,
        "user_id": user_id_claim,
        "token_hash": hash_token(cookie_token),
    }


def cookie_rate_limited_factory():
    """Factory for a dependency that enforces the per-token cookie rate limit."""

    async def cookie_rate_limited(
        request: Request,
        claims: dict = Depends(get_cookie_claims),
    ) -> dict:
        client_ip = extract_client_ip(request)
        token_hash = claims["token_hash"]
        try:
            allowed, retry_after = await _ensure_cookie_ratelimit(token_hash)
        except RateLimitServiceUnavailable:
            log_message_for_ip(client_ip, "Cookie rate limiter unavailable: Redis is not reachable.", PRINT_PREFIX, level="ERROR")
            raise api_error(503, "Rate limiter service unavailable.")

        if not allowed:
            log_message_for_ip(
                client_ip,
                f"Cookie rate limit exceeded username={claims['username']} retry_after={retry_after:.2f}s",
                PRINT_PREFIX,
                level="WARNING",
            )
            raise api_error(429, "Rate limit exceeded.", retry_after)
        return claims

    return cookie_rate_limited


async def get_current_cookie_data(
    request: Request,
    claims: dict = Depends(cookie_rate_limited_factory()),
) -> CookieRequestData:
    """Dependency that resolves the DB-backed cookie row and the user's current permissions."""
    client_ip = extract_client_ip(request)
    token_hash = claims["token_hash"]
    username_claim = claims["username"]
    user_id_claim = claims["user_id"]

    cookie_row = await _resolve_cookie_row(token_hash)
    if cookie_row is None:
        log_message_for_ip(
            client_ip,
            f"Cookie authentication failed: unregistered token hash={token_hash[:12]}",
            PRINT_PREFIX,
            level="WARNING",
        )
        raise api_error(401, "Cookie token is not registered.")
    if cookie_row["revoked"]:
        log_message_for_ip(
            client_ip,
            f"Cookie authentication failed: revoked token hash={token_hash[:12]}",
            PRINT_PREFIX,
            level="WARNING",
        )
        raise api_error(401, "Cookie token has been revoked.")

    cookie_expires_at = datetime.fromisoformat(cookie_row["expires_at"]) if cookie_row["expires_at"] else None
    if cookie_expires_at is None or cookie_expires_at <= datetime.now(timezone.utc):
        log_message_for_ip(
            client_ip,
            f"Cookie authentication failed: expired token hash={token_hash[:12]}",
            PRINT_PREFIX,
            level="WARNING",
        )
        raise api_error(401, "Cookie token has expired.")

    username = cookie_row["username"]
    if username != username_claim:
        log_message_for_ip(client_ip, "Cookie authentication failed: username claim mismatch.", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Invalid cookie token payload.")

    if user_id_claim is not None and cookie_row["user_id"] != user_id_claim:
        log_message_for_ip(client_ip, "Cookie authentication failed: user_id claim mismatch.", PRINT_PREFIX, level="WARNING")
        raise api_error(401, "Invalid cookie token payload.")

    try:
        permissions = await _resolve_user_permissions(username)
    except PermissionServiceUnavailable:
        log_message_for_ip(client_ip, "User permissions cache unavailable.", PRINT_PREFIX, level="ERROR")
        raise api_error(503, "Authorization cache unavailable.")

    if permissions is None:
        log_message_for_ip(
            client_ip,
            f"Cookie authentication failed: user not found username={username}",
            PRINT_PREFIX,
            level="WARNING",
        )
        raise api_error(401, "User no longer exists.")

    roles = permissions.get("roles") or []
    effective_role = str(permissions.get("role") or (roles[0] if roles else "")).lower()

    log_message_for_ip(
        client_ip,
        f"Cookie authentication accepted username={username} role={effective_role} token_hash={token_hash[:12]}",
        PRINT_PREFIX,
        level="INFO",
    )

    return CookieRequestData(
        username=username,
        user_id=cookie_row["user_id"],
        role=effective_role,
        token_hash=token_hash[:12],
        rate_limit=COOKIE_DEFAULT_RATE_LIMIT,
    )


def cookie_authorized_factory(required_roles: set[str] | None = None):
    """Factory to create a dependency that additionally checks for one of the required roles.

    Depends chain: get_cookie_claims (decode/shape) -> cookie_rate_limited (per-token rate limit)
    -> get_current_cookie_data (DB validity + permissions) -> this (role check).
    On success, the resolved `CookieRequestData` is stashed on `request.state.cookie_data`, and the caller's
    identity is recorded as the current audit-log actor (see audit_context.py) for any CRUD writes made later
    in the same request.
    """
    normalized_roles = {role.lower() for role in (required_roles or set())}

    async def cookie_authorized(
        request: Request,
        cookie_data: CookieRequestData = Depends(get_current_cookie_data),
    ) -> CookieRequestData:
        if normalized_roles and cookie_data.role not in normalized_roles:
            client_ip = extract_client_ip(request)
            log_message_for_ip(
                client_ip,
                "Cookie authentication failed: insufficient role "
                f"username={cookie_data.username} required_roles={sorted(normalized_roles)} "
                f"found_role={cookie_data.role}",
                PRINT_PREFIX,
                level="WARNING",
            )
            raise api_error(403, "Insufficient role.")

        request.state.cookie_data = cookie_data
        set_audit_actor(user_id=cookie_data.user_id, ip_address=extract_client_ip(request))
        return cookie_data

    return cookie_authorized
