from datetime import datetime

from sqlalchemy import delete, select

from src.models.database import SessionLocal
from src.models.tables.system.persistent_logs import PersistentLog, LOG_LEVEL, LOG_TYPES
from src.services.logging import log_message

PRINT_PREFIX = "PERSISTENT LOGS CRUD"


async def add_persistent_log(log_type: LOG_TYPES, log_level: LOG_LEVEL, message: str) -> PersistentLog:
    """Create and persist a log row."""
    async with SessionLocal() as session:
        row = PersistentLog(log_type=log_type, log_level=log_level, message=message)
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row


async def safe_add_persistent_log(log_type: LOG_TYPES, log_level: LOG_LEVEL, message: str) -> None:
    """Best-effort persistent logging that never raises to callers."""
    try:
        await add_persistent_log(log_type=log_type, log_level=log_level, message=message)
    except Exception as exc:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Failed to persist log row: {exc}")


async def get_persistent_logs(
    limit: int = 100,
    log_type: LOG_TYPES | None = None,
    log_level: LOG_LEVEL | None = None,
) -> list[PersistentLog]:
    """Return recent persistent logs, newest first."""
    async with SessionLocal() as session:
        stmt = select(PersistentLog).order_by(PersistentLog.created_at.desc()).limit(limit)
        if log_type is not None:
            stmt = stmt.where(PersistentLog.log_type == log_type)
        if log_level is not None:
            stmt = stmt.where(PersistentLog.log_level == log_level)
        result = await session.execute(stmt)
        return result.scalars().all()


async def get_persistent_log_by_id(log_id: int) -> PersistentLog | None:
    """Get a persistent log row by id."""
    async with SessionLocal() as session:
        stmt = select(PersistentLog).where(PersistentLog.id == log_id)
        result = await session.execute(stmt)
        return result.scalar_one_or_none()


async def update_persistent_log_message(log_id: int, new_message: str) -> PersistentLog | None:
    """Update the message field for an existing persistent log row."""
    async with SessionLocal() as session:
        stmt = select(PersistentLog).where(PersistentLog.id == log_id)
        result = await session.execute(stmt)
        row = result.scalar_one_or_none()
        if row is None:
            return None
        row.message = new_message
        await session.commit()
        await session.refresh(row)
        return row


async def delete_persistent_log(log_id: int) -> bool:
    """Delete a persistent log row by id."""
    async with SessionLocal() as session:
        stmt = delete(PersistentLog).where(PersistentLog.id == log_id)
        result = await session.execute(stmt)
        await session.commit()
        return (result.rowcount or 0) > 0


async def delete_persistent_logs_older_than(cutoff: datetime) -> int:
    """Delete log rows older than a given timestamp."""
    async with SessionLocal() as session:
        stmt = delete(PersistentLog).where(PersistentLog.created_at < cutoff)
        result = await session.execute(stmt)
        await session.commit()
        return result.rowcount or 0
