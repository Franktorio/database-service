from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from src.services.system.monitoring import monitored
from src.models.database import with_session
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.crud.cache_invalidation import (
    cache_invalidating,
    invalidate_cookie_cache,
    invalidate_user_permission_cache,
)
from src.models.tables.system.auth_cookie_table import AuthCookie
from src.models.tables.system.user_table import User
from src.services.system.logging import log_message

PRINT_PREFIX = "AUTH COOKIE CRUD"


async def _invalidate_after_update_auth_cookie(result, *args, **kwargs) -> None:
    if not isinstance(result, AuthCookie):
        return
    old_token_hash = kwargs.get("token_hash")
    if old_token_hash is None and args:
        old_token_hash = args[0]
    if isinstance(old_token_hash, str):
        await invalidate_cookie_cache(old_token_hash)
    await invalidate_cookie_cache(result.token_hash)


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_update_auth_cookie)
@with_session
async def add_auth_cookie(
    token_hash: str,
    user: User,
    expires_at: datetime,
    session: AsyncSession | None = None,
) -> AuthCookie:
    """Add a cookie JWT tracking row."""
    auth_cookie = AuthCookie(
        token_hash=token_hash,
        user_id=user.id,
        expires_at=expires_at,
    )
    session.add(auth_cookie)
    await session.commit()
    await session.refresh(auth_cookie)

    return auth_cookie


@monitored(measuring="db", operation_type="read")
@with_session
async def get_auth_cookie_by_hash(token_hash: str, session: AsyncSession | None = None) -> AuthCookie | None:
    """Fetch a cookie JWT tracking row by token hash."""
    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Auth cookie not found for provided hash.")

    return row


@monitored(measuring="db", operation_type="read")
@with_session
async def get_auth_cookies_by_uid(user_id: int, session: AsyncSession | None = None) -> list[AuthCookie]:
    """Fetch all cookie JWT tracking rows for a specific user ID."""
    stmt = select(AuthCookie).where(AuthCookie.user_id == user_id)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    return rows


@monitored(measuring="db", operation_type="write")
@with_session
async def revoke_auth_cookie(token_hash: str, session: AsyncSession | None = None) -> bool:
    """Mark a cookie JWT tracking row as revoked."""
    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No auth cookie found to revoke.")
        return False

    row.revoked = True
    await session.commit()
    await invalidate_cookie_cache(token_hash)

    return True


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_update_auth_cookie)
@with_session
async def refresh_auth_cookie(
    token_hash: str,
    new_token_hash: str,
    new_expires_at: datetime,
    session: AsyncSession | None = None,
) -> AuthCookie | None:
    """Rotate a cookie JWT tracking row to a new hash and expiration."""
    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No auth cookie found to refresh.")
        return None

    row.token_hash = new_token_hash
    row.expires_at = new_expires_at
    row.revoked = False
    await session.commit()
    await session.refresh(row)

    return row


@monitored(measuring="db", operation_type="write")
@with_session
async def revoke_expired_auth_cookies(
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Mark expired cookie JWT tracking rows as revoked."""
    check_time = now or datetime.now(timezone.utc)
    stale_stmt = select(AuthCookie.token_hash).where(
        AuthCookie.expires_at <= check_time, AuthCookie.revoked.is_(False)
    )
    stale_result = await session.execute(stale_stmt)
    stale_token_hashes = [row[0] for row in stale_result.all()]

    stmt = (
        update(AuthCookie)
        .where(AuthCookie.expires_at <= check_time, AuthCookie.revoked.is_(False))
        .values(revoked=True)
    )
    result = await session.execute(stmt)
    await session.commit()
    revoked = result.rowcount or 0
    for token_hash in stale_token_hashes:
        await invalidate_cookie_cache(token_hash)

    return revoked


@monitored(measuring="db", operation_type="write")
@with_session
async def delete_expired_auth_cookies(
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Delete expired cookie JWT tracking rows."""
    check_time = now or datetime.now(timezone.utc)
    stale_stmt = select(AuthCookie.token_hash).where(AuthCookie.expires_at <= check_time)
    stale_result = await session.execute(stale_stmt)
    stale_token_hashes = [row[0] for row in stale_result.all()]

    stmt = delete(AuthCookie).where(AuthCookie.expires_at <= check_time)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0
    for token_hash in stale_token_hashes:
        await invalidate_cookie_cache(token_hash)

    return deleted


@monitored(measuring="db", operation_type="write")
@with_session
async def delete_auth_cookies_by_username(username: str, session: AsyncSession | None = None) -> int:
    """Delete all auth cookies for a specific user. Used in user updates and deletions coupled in the same session."""
    user_id_subquery = select(User.id).where(User.username == username)

    stale_stmt = select(AuthCookie.token_hash).where(AuthCookie.user_id.in_(user_id_subquery))
    stale_result = await session.execute(stale_stmt)
    token_hashes = [row[0] for row in stale_result.all()]

    stmt = delete(AuthCookie).where(AuthCookie.user_id.in_(user_id_subquery))
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0
    for token_hash in token_hashes:
        await invalidate_cookie_cache(token_hash)
    await invalidate_user_permission_cache(username)

    return deleted