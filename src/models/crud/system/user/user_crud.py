# ~/src/models/crud/system/user/user_crud.py

from sqlalchemy import select, delete, update
from src.services.system.monitoring import monitored
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import with_session
from src.models.crud.cache_invalidation import cache_invalidating, invalidate_user_cache
from src.models.crud.system.audit_log_crud import audit_logged
from src.models.crud.system.auth_cookie_crud import delete_auth_cookies_by_username
from src.models.crud.system.user.user_role_crud import (
    assign_role_to_user,
    get_roles_for_user,
    remove_role_from_user,
    replace_user_roles,
)
from src.models.tables.system.users.user_table import User
from src.services.system.logging import log_message

PRINT_PREFIX = "USER CRUD"


async def _invalidate_after_user_write(result, *args, **kwargs) -> None:
    """Shared invalidator for user CRUD writes; see cache_invalidation.cache_invalidating."""
    if isinstance(result, User):
        await invalidate_user_cache(result.username)
    elif result is True:
        username = kwargs.get("username")
        if username is None and args:
            username = args[0]
        if isinstance(username, str):
            await invalidate_user_cache(username)


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.create')
@with_session
async def create_user(
    username: str,
    password_hash: str,
    initial_role: str,
    email: str = "",
    password_salt: str = "",
    hash_iterations: int = 210000,
    hash_algorithm: str = "pbkdf2_sha256",
    login_rate_limit: int = 10,
    session: AsyncSession | None = None,
) -> User:
    """Create a new user, granting them their initial role."""
    normalized_role = initial_role.strip().lower()
    if not normalized_role:
        raise ValueError("User creation requires a non-empty role.")

    new_user = User(
        username=username,
        password_hash=password_hash,
        email=email,
        password_salt=password_salt,
        hash_iterations=hash_iterations,
        hash_algorithm=hash_algorithm,
        login_rate_limit=login_rate_limit,
    )

    session.add(new_user)
    await session.commit()
    await session.refresh(new_user)

    await assign_role_to_user(new_user.id, normalized_role, session=session)

    log_message(f"{PRINT_PREFIX}: Created user '{username}'")
    return new_user


async def _apply_user_update(username: str, session: AsyncSession, **new_values) -> User | None:
    """Shared field-update logic for update_user/update_user_password/update_user_login_rate_limit.

    Revokes the user's existing auth cookies first if a session-invalidating field
    (username, password, or email) is being changed - mirrors the pre-refactor behavior.
    """
    session_invalidating = ("new_username", "new_password_hash", "new_email")
    if any(new_values.get(field) is not None for field in session_invalidating):
        await delete_auth_cookies_by_username(username, session=session)

    stmt = (
        update(User)
        .where(User.username == username)
        .values(
            username=new_values.get("new_username") if new_values.get("new_username") is not None else User.username,
            password_hash=new_values.get("new_password_hash") if new_values.get("new_password_hash") is not None else User.password_hash,
            email=new_values.get("new_email") if new_values.get("new_email") is not None else User.email,
            password_salt=new_values.get("new_password_salt") if new_values.get("new_password_salt") is not None else User.password_salt,
            hash_iterations=new_values.get("new_hash_iterations") if new_values.get("new_hash_iterations") is not None else User.hash_iterations,
            hash_algorithm=new_values.get("new_hash_algorithm") if new_values.get("new_hash_algorithm") is not None else User.hash_algorithm,
            login_rate_limit=new_values.get("new_login_rate_limit") if new_values.get("new_login_rate_limit") is not None else User.login_rate_limit,
        )
        .returning(User)
    )
    result = await session.execute(stmt)
    updated_user = result.scalar_one_or_none()
    await session.commit()

    if updated_user:
        log_message(f"{PRINT_PREFIX}: Updated user '{username}'")
    else:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No user found to update for username '{username}'")

    return updated_user


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.update')
@with_session
async def update_user(
    username: str,
    new_username: str | None = None,
    new_email: str | None = None,
    session: AsyncSession | None = None,
) -> User | None:
    """Update a user's username and/or email. Use update_user_password/update_user_login_rate_limit for those fields."""
    return await _apply_user_update(username, session, new_username=new_username, new_email=new_email)


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.password_update')
@with_session
async def update_user_password(
    username: str,
    new_password_hash: str,
    new_password_salt: str,
    new_hash_iterations: int = 210000,
    new_hash_algorithm: str = "pbkdf2_sha256",
    session: AsyncSession | None = None,
) -> User | None:
    """Rotate a user's password hash/salt/iterations/algorithm."""
    return await _apply_user_update(
        username,
        session,
        new_password_hash=new_password_hash,
        new_password_salt=new_password_salt,
        new_hash_iterations=new_hash_iterations,
        new_hash_algorithm=new_hash_algorithm,
    )


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.login_rate_limit_update')
@with_session
async def update_user_login_rate_limit(
    username: str,
    new_login_rate_limit: int,
    session: AsyncSession | None = None,
) -> User | None:
    """Update a user's login rate limit."""
    return await _apply_user_update(username, session, new_login_rate_limit=new_login_rate_limit)


@monitored(measuring="db", operation_type="write")
@audit_logged('user.roles_update')
@with_session
async def set_user_roles(
    username: str,
    set_roles: list[str] | None = None,
    add_role: str | None = None,
    remove_role: str | None = None,
    session: AsyncSession | None = None,
) -> list[str] | None:
    """Add/remove/replace a user's role assignments. Returns the resulting role list, or None if the user doesn't exist."""
    user = await get_user_by_username(username, session=session)
    if user is None:
        return None

    current_roles = await get_roles_for_user(user.id, session=session)

    if set_roles is not None:
        normalized_roles: list[str] = []
        for role_name in set_roles:
            normalized = role_name.strip().lower()
            if not normalized:
                raise ValueError("set_roles cannot contain empty role values.")
            if normalized not in normalized_roles:
                normalized_roles.append(normalized)

        if not normalized_roles:
            raise ValueError("set_roles must contain at least one role.")

        current_roles = await replace_user_roles(user.id, normalized_roles, session=session)
    else:
        if add_role is not None:
            normalized_add = add_role.strip().lower()
            if not normalized_add:
                raise ValueError("add_role must be non-empty when provided.")
            if normalized_add not in current_roles:
                await assign_role_to_user(user.id, normalized_add, session=session)
                current_roles.append(normalized_add)

        if remove_role is not None:
            normalized_remove = remove_role.strip().lower()
            if not normalized_remove:
                raise ValueError("remove_role must be non-empty when provided.")
            if normalized_remove in current_roles:
                if len(current_roles) == 1:
                    raise ValueError("Cannot remove the last remaining role from a user.")
                await remove_role_from_user(user.id, normalized_remove, session=session)
                current_roles = [role for role in current_roles if role != normalized_remove]

    await delete_auth_cookies_by_username(username, session=session)
    await invalidate_user_cache(username)

    return current_roles


@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.delete')
@with_session
async def delete_user(username: str, session: AsyncSession | None = None) -> bool:
    """Delete a user by their username. Auth cookies and role assignments cascade on delete."""

    stmt = delete(User).where(User.username == username)
    result = await session.execute(stmt)
    await session.commit()

    if result.rowcount > 0:
        log_message(f"{PRINT_PREFIX}: Deleted user '{username}'")
        return True
    else:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No user found to delete for username '{username}'")
        return False


@monitored(measuring="db", operation_type="read")
@with_session
async def get_user_by_username(username: str, session: AsyncSession | None = None) -> User | None:
    """Fetch a user by their username."""
    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found for provided username.")
    return user


@monitored(measuring="db", operation_type="read")
@with_session
async def get_user_by_id(user_id: int, session: AsyncSession | None = None) -> User | None:
    """Fetch a user by their internal id."""
    stmt = select(User).where(User.id == user_id)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found for provided id.")
    return user


@monitored(measuring="db", operation_type="read")
@with_session
async def get_users(session: AsyncSession | None = None) -> list[User]:
    """Fetch all users."""
    stmt = select(User).order_by(User.username)
    result = await session.execute(stmt)
    users = result.scalars().all()

    return users
