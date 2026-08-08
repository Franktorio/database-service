# ~/src/models/crud/system/user/role_crud.py

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.system.monitoring import monitored
from src.models.crud.system.audit_log_crud import audit_logged
from src.models.database import with_session
from src.models.tables.system.users.roles_table import Role
from src.models.tables.system.users.user_roles_table import UserRole
from src.services.system.logging import log_message

PRINT_PREFIX = "ROLE CRUD"

@audit_logged("role.create")
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


@audit_logged("role.update")
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
async def get_role_by_id(role_id: int, session: AsyncSession | None = None) -> Role | None:
    """Fetch a role by its internal id."""
    stmt = select(Role).where(Role.id == role_id)
    result = await session.execute(stmt)
    role = result.scalar_one_or_none()
    if role is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Role not found for provided id.")

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


@audit_logged("role.delete")
@monitored(measuring="db", operation_type="write")
@with_session
async def delete_role_by_id(role_id: int, session: AsyncSession | None = None) -> bool:
    """Delete a role by id if no user is currently assigned to it."""
    assignment_stmt = select(UserRole.id).where(UserRole.role_id == role_id).limit(1)
    assignment_result = await session.execute(assignment_stmt)
    assigned_role = assignment_result.scalar_one_or_none()
    if assigned_role is not None:
        raise ValueError(f"Role with ID {role_id} is assigned to one or more users and cannot be deleted.")

    stmt = delete(Role).where(Role.id == role_id)
    result = await session.execute(stmt)
    await session.commit()
    if result.rowcount and result.rowcount > 0:
        return True

    log_message(f"[WARNING] [{PRINT_PREFIX}] No role found to delete for provided id.")
    return False
