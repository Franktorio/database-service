import asyncio
from functools import wraps
import time
from datetime import datetime, timezone

from fastapi import HTTPException
from fastapi.responses import JSONResponse
from fastapi.responses import RedirectResponse
from starlette.responses import Response

from config.loader import COOKIE_DEFAULT_RATE_LIMIT
from src.api.config import COOKIE_JWT_INDEX
from src.models.crud.system.auth_cookie_crud import get_auth_cookie_by_hash
from src.models.crud.system.user_crud import get_user_by_username
from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.security.ratelimit import RateLimit, RateLimitServiceUnavailable
from src.security.tokens import decode_jwt_token, hash_token
from src.services.system.logging import log_message

_ratelimiters: dict[str, RateLimit] = {}
_last_seen_by_token: dict[str, float] = {}
_cache_lock = asyncio.Lock()


def _client_ip(request) -> str | None:
    client = getattr(request, "client", None)
    if client is not None:
        host = getattr(client, "host", None)
        if host:
            return host
    return None


def _place_in_ratelimiters(token_hash: str, rate_limit: int) -> RateLimit:
    current_time = time.time()
    _ratelimiters[token_hash] = RateLimit(
        limit=rate_limit,
        key_hash=token_hash,
    )
    _last_seen_by_token[token_hash] = current_time
    return _ratelimiters[token_hash]


async def cleanup_inactive_cookie_ratelimiters(max_inactive_seconds: int) -> int:
    """Remove cached cookie ratelimiters that have been inactive for too long."""
    now = time.time()
    removed = 0
    stale_limiters: list[RateLimit] = []
    async with _cache_lock:
        stale_hashes = [
            token_hash
            for token_hash, last_seen in _last_seen_by_token.items()
            if (now - last_seen) >= max_inactive_seconds
        ]
        for token_hash in stale_hashes:
            _last_seen_by_token.pop(token_hash, None)
            limiter = _ratelimiters.pop(token_hash, None)
            if limiter is not None:
                stale_limiters.append(limiter)
                removed += 1

    for limiter in stale_limiters:
        try:
            await limiter.delete()
        except RateLimitServiceUnavailable:
            # Cleanup should not fail request handling when Redis is down.
            pass
    return removed


async def _obtain_ratelimit(token_hash: str) -> RateLimit:
    async with _cache_lock:
        existing = _ratelimiters.get(token_hash)
        if existing is not None:
            _last_seen_by_token[token_hash] = time.time()
            return existing

        limiter = _place_in_ratelimiters(
            token_hash,
            COOKIE_DEFAULT_RATE_LIMIT,
        )
        _last_seen_by_token[token_hash] = time.time()
        return limiter

def cookie_authentication(required_roles: set[str] | None = None, redirect_url: str | None = None):
    """Decorator that validates a cookie JWT, enforces optional role checks, and per-token rate limits."""
    normalized_roles = {role.lower() for role in (required_roles or set())}

    def decorator(func):
        @wraps(func)
        async def wrapper(request, *args, **kwargs):
            client_ip = _client_ip(request)
            cookie_token = request.cookies.get(COOKIE_JWT_INDEX)
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

            token_hash = hash_token(cookie_token)
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

            username = cookie_row.username # Use the username from the database row instead of the JWT payload to prevent tampering
            if not username:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message="Cookie authentication failed: missing username claim",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="Invalid cookie token payload.")

            user = await get_user_by_username(username)
            if user is None:
                await safe_add_persistent_log(
                    log_type="USER AUTH",
                    log_level="WARNING",
                    message=f"Cookie authentication failed: user not found username={username}",
                    ip_address=client_ip,
                )
                if redirect_url:
                    return RedirectResponse(url=redirect_url)
                raise HTTPException(status_code=401, detail="User no longer exists.")

            effective_role = (user.role or "").lower()
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

            ratelimit = await _obtain_ratelimit(token_hash)

            try:
                allowed, status = await ratelimit.is_allowed()
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
                        f"username={username} retry_after={status:.2f}s"
                    ),
                    ip_address=client_ip,
                )
                raise HTTPException(
                    status_code=429,
                    detail={"error": "Rate limit exceeded.", "retry_after": status},
                )

            seconds_since_last_request = 0.0
            try:
                seconds_since_last_request = await ratelimit.how_long_ago()
            except RateLimitServiceUnavailable:
                # Keep the request successful even if optional limiter telemetry is unavailable.
                seconds_since_last_request = 0.0

            request._cookie_data = {
                "username": username,
                "role": effective_role,
                "token_hash": token_hash[:12],
                "rate_limit": ratelimit.limit,
                "requests_remaining": int(status) if allowed else 0,
                "seconds_since_last_request": seconds_since_last_request,
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
