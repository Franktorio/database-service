from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.models.database import SessionLocal
from src.models.tables.system.persistent_logs import PersistentLog, LOG_LEVEL, LOG_TYPES
from src.services.system.logging import log_message

PRINT_PREFIX = "PERSISTENT LOGS CRUD"


async def add_persistent_log(
    log_type: LOG_TYPES,
    log_level: LOG_LEVEL,
    message: str,
    session: AsyncSession | None = None,
) -> PersistentLog:
    """Create and persist a log row."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    row = PersistentLog(log_type=log_type, log_level=log_level, message=message)
    session.add(row)
    await session.commit()
    await session.refresh(row)

    if close_session:
        await session.close()

    return row


async def add_persistent_log_with_ip(
    log_type: LOG_TYPES,
    log_level: LOG_LEVEL,
    message: str,
    ip_address: str | None = None,
    session: AsyncSession | None = None,
) -> PersistentLog:
    """Create and persist a log row with an optional source IP."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    row = PersistentLog(
        log_type=log_type,
        log_level=log_level,
        message=message,
        ip_address=ip_address,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)

    if close_session:
        await session.close()

    return row


async def safe_add_persistent_log(
    log_type: LOG_TYPES,
    log_level: LOG_LEVEL,
    message: str,
    ip_address: str | None = None,
    session: AsyncSession | None = None,
) -> None:
    """Best-effort persistent logging that never raises to callers."""
    try:
        await add_persistent_log_with_ip(
            log_type=log_type,
            log_level=log_level,
            message=message,
            ip_address=ip_address,
            session=session,
        )
    except Exception as exc:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Failed to persist log row: {exc}")


async def get_persistent_logs(
    limit: int = 100,
    log_type: LOG_TYPES | None = None,
    log_level: LOG_LEVEL | None = None,
    session: AsyncSession | None = None,
) -> list[PersistentLog]:
    """Return recent persistent logs, newest first."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(PersistentLog).order_by(PersistentLog.created_at.desc()).limit(limit)
    if log_type is not None:
        stmt = stmt.where(PersistentLog.log_type == log_type)
    if log_level is not None:
        stmt = stmt.where(PersistentLog.log_level == log_level)
    result = await session.execute(stmt)
    rows = result.scalars().all()

    if close_session:
        await session.close()

    return rows


async def get_persistent_log_by_id(log_id: int, session: AsyncSession | None = None) -> PersistentLog | None:
    """Get a persistent log row by id."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(PersistentLog).where(PersistentLog.id == log_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()

    if close_session:
        await session.close()

    return row


async def update_persistent_log_message(
    log_id: int,
    new_message: str,
    session: AsyncSession | None = None,
) -> PersistentLog | None:
    """Update the message field for an existing persistent log row."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(PersistentLog).where(PersistentLog.id == log_id)
    result = await session.execute(stmt)
    row = result.scalar_one_or_none()
    if row is None:
        if close_session:
            await session.close()
        return None
    row.message = new_message
    await session.commit()
    await session.refresh(row)

    if close_session:
        await session.close()

    return row


async def delete_persistent_log(log_id: int, session: AsyncSession | None = None) -> bool:
    """Delete a persistent log row by id."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = delete(PersistentLog).where(PersistentLog.id == log_id)
    result = await session.execute(stmt)
    await session.commit()
    deleted = (result.rowcount or 0) > 0

    if close_session:
        await session.close()

    return deleted


async def delete_persistent_logs_older_than(cutoff: datetime, session: AsyncSession | None = None) -> int:
    """Delete log rows older than a given timestamp."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = delete(PersistentLog).where(PersistentLog.created_at < cutoff)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount or 0

    if close_session:
        await session.close()

    return deleted
