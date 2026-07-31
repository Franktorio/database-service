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
async def create_role(name: str, description: str = "", session: AsyncSession | None = None) -> Role:
    """Create a new role with the given name and description."""
    normalized_name = name.strip().lower()
    existing_role = await get_role_by_name(normalized_name, session=session)
    if existing_role:
        raise ValueError(f"Role '{normalized_name}' already exists.")

    new_role = Role(name=normalized_name, description=description)
    session.add(new_role)
    await session.commit()
    await session.refresh(new_role)
    return new_role


@monitored(measuring="db", operation_type="write")
@with_session
async def update_role(role_id: int, new_name: str | None = None, new_description: str | None = None, session: AsyncSession | None = None) -> Role:
    """Update an existing role's name and/or description."""
    stmt = select(Role).where(Role.id == role_id)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()
    if not role:
        raise ValueError(f"Role with ID {role_id} does not exist.")

    if new_name:
        normalized_name = new_name.strip().lower()
        existing_role = await get_role_by_name(normalized_name, session=session)
        if existing_role and existing_role.id != role_id:
            raise ValueError(f"Role '{normalized_name}' already exists.")
        role.name = normalized_name

    if new_description is not None:
        role.description = new_description

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
