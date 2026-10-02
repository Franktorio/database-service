"""Shared signed-session renewal; application authorization stays in route dependencies."""

from datetime import datetime, timezone

from fastapi import Request
from fastapi.responses import JSONResponse

from config.loader import JWT_EXP_MINUTES
from src.api.config import COOKIE_JWT_INDEX
from src.api.errors import api_error
from src.models.crud.system.auth_cookie_crud import revoke_auth_cookie, update_expires_at_for_auth_cookie
from src.security.tokens import cookie_session_hash, create_cookie_token, create_jwt_token, decode_jwt_token, get_cookie_settings
from src.services.system.logging import log_message


SESSION_HEADERS = {"Cache-Control": "no-store"}


def session_claims(request: Request) -> dict:
    claims = decode_jwt_token(request.cookies.get(COOKIE_JWT_INDEX, ""))
    if claims is None or type(claims.get("exp")) is not int:
        raise api_error(401, "Cookie token has expired.")
    return claims


def session_metadata(request: Request) -> dict:
    """Report the actual signed expiry rather than the database cleanup deadline."""
    claims = session_claims(request)
    issued_at = claims.get("iat", claims["exp"])
    if type(issued_at) is not int:
        raise api_error(401, "Invalid cookie token payload.")
    return {
        "session_expires_at": datetime.fromtimestamp(claims["exp"], timezone.utc).isoformat(),
        "session_lifetime_seconds": max(1, claims["exp"] - issued_at),
    }


async def refresh_session(request: Request, cookie_data, *, expires_minutes: int = JWT_EXP_MINUTES) -> JSONResponse:
    """Renew an authorized session, preserving its revocation and rate-limit identity."""
    claims = session_claims(request)
    token_hash = cookie_session_hash(request.cookies[COOKIE_JWT_INDEX], claims)
    if token_hash != cookie_data.token_hash:
        raise api_error(401, "Invalid session identity.")
    session_id = claims.get("sid")
    if isinstance(session_id, str) and len(session_id) >= 32:
        token, expires_at = create_jwt_token(
            cookie_data.username, cookie_data.role, cookie_data.user_id,
            expires_minutes=expires_minutes, session_id=session_id,
        )
        renewed = await update_expires_at_for_auth_cookie(token_hash, expires_at)
        if renewed is None:
            raise api_error(401, "Session is no longer active.")
    else:
        # Upgrade a valid pre-sid cookie without leaving its old session usable.
        token = await create_cookie_token(cookie_data.username, cookie_data.role, expires_minutes=expires_minutes)
        refreshed_claims = decode_jwt_token(token)
        if refreshed_claims is None:
            raise api_error(401, "Session could not be renewed.")
        expires_at = datetime.fromtimestamp(refreshed_claims["exp"], timezone.utc)
        revoked = await revoke_auth_cookie(token_hash)
        if not revoked:
            await revoke_auth_cookie(cookie_session_hash(token, refreshed_claims))
            raise api_error(401, "Session is no longer active.")
    response = JSONResponse(
        content={"message": "Session refreshed.", "session_expires_at": expires_at.isoformat()},
        headers=SESSION_HEADERS,
    )
    response.set_cookie(**get_cookie_settings(expires_minutes=expires_minutes), value=token)
    log_message(f"[INFO] [SESSION] Cookie renewed user_id={cookie_data.user_id}")
    return response
