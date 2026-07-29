# ~/src/models/crud/system/audit_log_crud.py
# Read-only-from-the-API audit trail. Every mutating write in the other system CRUD
# modules (api_key_crud.py, user_crud.py) is recorded here via the `audit_logged`
# decorator, attributed to whichever identity is current in `audit_context` (the
# SUPER_ADMIN API key or authenticated user that made the request). There are no
# update/delete functions here by design - audit logs are append-only.

from functools import wraps

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.system.monitoring import monitored
from src.models.crud.audit_context import get_audit_actor
from src.models.database import with_session
from src.models.tables.system.audit_log_table import AuditLog
from src.services.system.logging import log_message

PRINT_PREFIX = "AUDIT LOG CRUD"

MAX_AUDIT_LOG_PAGE_SIZE = 500


@monitored(measuring="db", operation_type="write")
@with_session
async def add_audit_log(
    action: str,
    user_id: int | None = None,
    api_key_id: int | None = None,
    ip_address: str = "",
    session: AsyncSession | None = None,
) -> AuditLog:
    """Append an audit log entry. Audit logs are append-only; there is no update/delete."""
    audit_log = AuditLog(action=action, user_id=user_id, api_key_id=api_key_id, ip_address=ip_address)
    session.add(audit_log)
    await session.commit()
    await session.refresh(audit_log)

    return audit_log


@monitored(measuring="db", operation_type="read")
@with_session
async def get_audit_logs(
    limit: int = 100,
    offset: int = 0,
    session: AsyncSession | None = None,
) -> list[AuditLog]:
    """Fetch audit logs, most recent first. `limit` is capped at `MAX_AUDIT_LOG_PAGE_SIZE`."""
    bounded_limit = max(1, min(limit, MAX_AUDIT_LOG_PAGE_SIZE))
    stmt = (
        select(AuditLog)
        .order_by(AuditLog.timestamp.desc())
        .limit(bounded_limit)
        .offset(max(0, offset))
    )
    result = await session.execute(stmt)
    audit_logs = result.scalars().all()

    return audit_logs


@monitored(measuring="db", operation_type="read")
@with_session
async def get_audit_log_by_id(log_id: int, session: AsyncSession | None = None) -> AuditLog | None:
    """Fetch a single audit log entry by its id."""
    stmt = select(AuditLog).where(AuditLog.id == log_id)
    result = await session.execute(stmt)
    audit_log = result.scalar_one_or_none()
    if audit_log is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Audit log not found for provided id.")

    return audit_log


def audit_logged(action: str):
    """Decorator factory: after the wrapped async CRUD write succeeds (returns a
    truthy value), append an audit log entry attributed to the current request's
    actor (see audit_context.py).

    A falsy result (`None`/`False`) means "nothing was written" (e.g. not found), so
    no audit entry is recorded in that case. Import this into any CRUD module whose
    writes should be tracked - since it wraps the function itself, a write can't
    reach the database without also being logged, regardless of which route (or
    script) calls it.

    Example:
        @audit_logged("user.create")
        @cache_invalidating(_invalidate_after_user_write)
        @with_session
        async def add_user(...): ...
    """

    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            if result:
                actor = get_audit_actor()
                await add_audit_log(
                    action=action,
                    user_id=actor.user_id,
                    api_key_id=actor.api_key_id,
                    ip_address=actor.ip_address,
                )
            return result

        return wrapper

    return decorator
