from datetime import datetime, timezone

from sqlalchemy import delete, select

from src.models.database import SessionLocal
from src.models.tables.auth_cookie_table import AuthCookie
from src.services.logging import log_message

PRINT_PREFIX = "AUTH COOKIE CRUD"


async def add_auth_cookie(
    token_hash: str,
    username: str,
    expires_at: datetime,
) -> AuthCookie:
    """Add a cookie JWT tracking row."""
    async with SessionLocal() as session:
        auth_cookie = AuthCookie(
            token_hash=token_hash,
            username=username,
            expires_at=expires_at,
        )
        session.add(auth_cookie)
        await session.commit()
        await session.refresh(auth_cookie)
        log_message(f"[INFO] [{PRINT_PREFIX}] Auth cookie row created with id {auth_cookie.id}.")
        return auth_cookie


async def get_auth_cookie_by_hash(token_hash: str) -> AuthCookie | None:
    """Fetch a cookie JWT tracking row by token hash."""
    async with SessionLocal() as session:
        stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            log_message(f"[WARNING] [{PRINT_PREFIX}] Auth cookie not found for provided hash.")
        return row


async def revoke_auth_cookie(token_hash: str) -> bool:
    """Mark a cookie JWT tracking row as revoked."""
    async with SessionLocal() as session:
        stmt = select(AuthCookie).where(AuthCookie.token_hash == token_hash)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            log_message(f"[WARNING] [{PRINT_PREFIX}] No auth cookie found to revoke.")
            return False

        row.revoked = True
        await session.commit()
        log_message(f"[INFO] [{PRINT_PREFIX}] Auth cookie revoked for hash.")
        return True


async def delete_expired_auth_cookies(now: datetime | None = None) -> int:
    """Delete expired cookie JWT tracking rows."""
    check_time = now or datetime.now(timezone.utc)
    async with SessionLocal() as session:
        stmt = delete(AuthCookie).where(AuthCookie.expires_at <= check_time)
        result = await session.execute(stmt)
        await session.commit()
        deleted = result.rowcount or 0
        if deleted > 0:
            log_message(f"[INFO] [{PRINT_PREFIX}] Deleted {deleted} expired auth cookie rows.")
        return deleted