# ~/src/models/crud/system/user/role_crud.py

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.system.monitoring import monitored
from src.models.database import with_session
from src.models.tables.system.users.roles_table import Role
from src.services.system.logging import log_message

PRINT_PREFIX = "ROLE CRUD"


@monitored(measuring="db", operation_type="write")
@with_session
async def get_or_create_role(name: str, description: str = "", session: AsyncSession | None = None) -> Role:
    """Fetch a role by name, creating it if it doesn't exist yet (roles are freeform, not pre-registered)."""
    normalized_name = name.strip().lower()
    stmt = select(Role).where(Role.name == normalized_name)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()
    if role is not None:
        return role

    role = Role(name=normalized_name, description=description)
    session.add(role)
    await session.commit()
    await session.refresh(role)

    return role


@monitored(measuring="db", operation_type="read")
@with_session
async def get_role_by_name(name: str, session: AsyncSession | None = None) -> Role | None:
    """Fetch a role by its (normalized) name."""
    stmt = select(Role).where(Role.name == name.strip().lower())
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()
    if role is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Role not found for provided name.")

    return role


@monitored(measuring="db", operation_type="read")
@with_session
async def get_roles(session: AsyncSession | None = None) -> list[Role]:
    """Fetch all defined roles."""
    stmt = select(Role).order_by(Role.name)
    result = await session.execute(stmt)
    roles = result.scalars().all()

    return roles
