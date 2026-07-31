# ~/src/models/crud/system/user/user_role_crud.py
# CRUD for the users<->roles many-to-many join table (user_roles).

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.services.system.monitoring import monitored
from src.models.database import with_session
from src.models.crud.system.user.role_crud import get_role_by_name
from src.models.tables.system.users.roles_table import Role
from src.models.tables.system.users.user_roles_table import UserRole
from src.services.system.logging import log_message

PRINT_PREFIX = "USER ROLE CRUD"


@monitored(measuring="db", operation_type="read")
@with_session
async def get_roles_for_user(user_id: int, session: AsyncSession | None = None) -> list[str]:
    """Fetch a user's assigned role names, oldest-granted first (the first entry is the "primary" role)."""
    stmt = (
        select(Role.name)
        .join(UserRole, UserRole.role_id == Role.id)
        .where(UserRole.user_id == user_id)
        .order_by(UserRole.created_at)
    )
    result = await session.execute(stmt)
    return [row[0] for row in result.all()]


@monitored(measuring="db", operation_type="read")
@with_session
async def get_roles_for_users(user_ids: list[int], session: AsyncSession | None = None) -> dict[int, list[str]]:
    """Bulk-fetch role names for multiple users at once (avoids N+1 queries for list endpoints)."""
    roles_by_user: dict[int, list[str]] = {user_id: [] for user_id in user_ids}
    if not user_ids:
        return roles_by_user

    stmt = (
        select(UserRole.user_id, Role.name)
        .join(Role, UserRole.role_id == Role.id)
        .where(UserRole.user_id.in_(user_ids))
        .order_by(UserRole.user_id, UserRole.created_at)
    )
    result = await session.execute(stmt)
    for user_id, role_name in result.all():
        roles_by_user.setdefault(user_id, []).append(role_name)

    return roles_by_user


@monitored(measuring="db", operation_type="write")
@with_session
async def assign_role_to_user(user_id: int, role_name: str, session: AsyncSession | None = None) -> UserRole:
    """Grant a role to a user, creating the role if it doesn't exist yet. No-op if already assigned."""
    role = await get_role_by_name(role_name, session=session)
    
    if role is None:
        raise ValueError(f"Role '{role_name}' does not exist and cannot be assigned to user {user_id}.")

    stmt = select(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    result = await session.execute(stmt)
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    user_role = UserRole(user_id=user_id, role_id=role.id)
    session.add(user_role)
    await session.commit()
    await session.refresh(user_role)

    return user_role


@monitored(measuring="db", operation_type="write")
@with_session
async def remove_role_from_user(user_id: int, role_name: str, session: AsyncSession | None = None) -> bool:
    """Revoke a role from a user. Returns False if the role or the assignment doesn't exist."""
    role = await get_role_by_name(role_name, session=session)
    if role is None:
        return False

    stmt = delete(UserRole).where(UserRole.user_id == user_id, UserRole.role_id == role.id)
    result = await session.execute(stmt)
    await session.commit()
    removed = result.rowcount > 0
    if not removed:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No role assignment found to remove for the provided user/role.")

    return removed


@monitored(measuring="db", operation_type="write")
@with_session
async def replace_user_roles(user_id: int, role_names: list[str], session: AsyncSession | None = None) -> list[str]:
    """Replace a user's entire set of role assignments with `role_names` (creating any missing roles)."""
    await session.execute(delete(UserRole).where(UserRole.user_id == user_id))
    for role_name in role_names:
        role = await get_role_by_name(role_name, session=session)
        if role is None:
            raise ValueError(f"Role '{role_name}' does not exist and cannot be assigned to user {user_id}.")
        session.add(UserRole(user_id=user_id, role_id=role.id))
    await session.commit()

    return list(role_names)
