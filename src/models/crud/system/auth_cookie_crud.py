from datetime import datetime, timezone

from sqlalchemy import delete, select, update

from src.models.database import SessionLocal
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.tables.system.auth_cookie_table import AuthCookie
from src.services.system.cache.permissionscache import remove_cached_permission_json
from src.services.system.cache.ratelimitcache import remove_from_redis
from src.services.system.logging import log_message

PRINT_PREFIX = "AUTH COOKIE CRUD"


async def _invalidate_cookie_cache(token_hash: str) -> None:
    await remove_from_redis(f"cookie:{token_hash}")


async def _invalidate_user_permission_cache(username: str) -> None:
    await remove_cached_permission_json(f"user:{username}")


async def add_auth_cookie(
    token_hash: str,
    username: str,
    expires_at: datetime,
    session: AsyncSession | None = None,
) -> AuthCookie:
    """Add a cookie JWT tracking row."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    auth_cookie = AuthCookie(
        token_hash=token_hash,
        username=username,
        expires_at=expires_at,
    )
    session.add(auth_cookie)
    await session.commit()
    await session.refresh(auth_cookie)
    await _invalidate_cookie_cache(token_hash)
    await _invalidate_user_permission_cache(username)
    log_message(f"[INFO] [{PRINT_PREFIX}] Auth cookie row created with id {auth_cookie.id}.")

    if close_session:
        await session.close()

    return auth_cookie


async def get_auth_cookie_by_hash(token_hash: str, session: AsyncSession | None = None) -> AuthCookie | None:
    """Fetch a cookie JWT tracking row by token hash."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Auth cookie not found for provided hash.")

    if close_session:
        await session.close()

    return row


async def revoke_auth_cookie(token_hash: str, session: AsyncSession | None = None) -> bool:
    """Mark a cookie JWT tracking row as revoked."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No auth cookie found to revoke.")
        if close_session:
            await session.close()
        return False

    row.revoked = True
    await session.commit()
    await _invalidate_cookie_cache(token_hash)
    await _invalidate_user_permission_cache(row.username)
    log_message(f"[INFO] [{PRINT_PREFIX}] Auth cookie revoked for hash.")

    if close_session:
        await session.close()

    return True


async def refresh_auth_cookie(
    token_hash: str,
    new_token_hash: str,
    new_expires_at: datetime,
    session: AsyncSession | None = None,
) -> AuthCookie | None:
    """Rotate a cookie JWT tracking row to a new hash and expiration."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No auth cookie found to refresh.")
        if close_session:
            await session.close()
        return None

    row.token_hash = new_token_hash
    row.expires_at = new_expires_at
    row.revoked = False
    old_token_hash = token_hash
    await session.commit()
    await session.refresh(row)
    await _invalidate_cookie_cache(old_token_hash)
    await _invalidate_cookie_cache(new_token_hash)
    await _invalidate_user_permission_cache(row.username)
    log_message(f"[INFO] [{PRINT_PREFIX}] Refreshed auth cookie row id {row.id}.")

    if close_session:
        await session.close()

    return row


async def revoke_expired_auth_cookies(
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Mark expired cookie JWT tracking rows as revoked."""
    check_time = now or datetime.now(timezone.utc)
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = (
        update(AuthCookie)
        .where(AuthCookie.expires_at <= check_time, AuthCookie.revoked.is_(False))
        .values(revoked=True)
    )
    result = await session.execute(stmt)
    await session.commit()
    revoked = result.rowcount or 0
    if revoked > 0:
        log_message(f"[INFO] [{PRINT_PREFIX}] Revoked {revoked} expired auth cookie rows.")

    if close_session:
        await session.close()

    return revoked


async def delete_expired_auth_cookies(
    now: datetime | None = None,
    session: AsyncSession | None = None,
) -> int:
    """Delete expired cookie JWT tracking rows."""
    check_time = now or datetime.now(timezone.utc)
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stale_stmt = select(AuthCookie.token_hash, AuthCookie.username).where(AuthCookie.expires_at <= check_time)
    stale_result = await session.execute(stale_stmt)
    stale_rows = stale_result.all()

    stmt = delete(AuthCookie).where(AuthCookie.expires_at <= check_time)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0
    for token_hash, username in stale_rows:
        await _invalidate_cookie_cache(token_hash)
        await _invalidate_user_permission_cache(username)
    if deleted > 0:
        log_message(f"[INFO] [{PRINT_PREFIX}] Deleted {deleted} expired auth cookie rows.")

    if close_session:
        await session.close()

    return deleted
    
async def delete_auth_cookies_by_username(username: str, session: AsyncSession | None = None) -> int:
    """Delete all auth cookies for a specific user. Used in user updates and deletions coupled in the same session."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stale_stmt = select(AuthCookie.token_hash).where(AuthCookie.username == username)
    stale_result = await session.execute(stale_stmt)
    token_hashes = [row[0] for row in stale_result.all()]

    stmt = delete(AuthCookie).where(AuthCookie.username == username)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0
    for token_hash in token_hashes:
        await _invalidate_cookie_cache(token_hash)
    await _invalidate_user_permission_cache(username)
    if deleted > 0:
        log_message(f"[INFO] [{PRINT_PREFIX}] Deleted {deleted} auth cookie rows for user {username}.")

    if close_session:
        await session.close()

    return deleted