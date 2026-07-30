# ~/src/models/crud/system/user_crud.py

from sqlalchemy import select, delete, update
from src.services.system.monitoring import monitored
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import with_session
from src.models.crud.cache_invalidation import cache_invalidating, invalidate_user_cache
from src.models.crud.system.audit_log_crud import audit_logged
from src.models.crud.system.auth_cookie_crud import delete_auth_cookies_by_username
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
    email: str = "",
    password_salt: str = "",
    hash_iterations: int = 210000,
    hash_algorithm: str = "pbkdf2_sha256",
    login_rate_limit: int = 10,
    session: AsyncSession | None = None,
) -> User:
    """Create a new user in the database."""

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

    log_message(f"{PRINT_PREFIX}: Created user '{username}'")
    return new_user

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

@monitored(measuring="db", operation_type="write")
@cache_invalidating(_invalidate_after_user_write)
@audit_logged('user.update')
@with_session
async def update_user(
    username: str,
    new_username: str | None = None,
    new_password_hash: str | None = None,
    new_email: str | None = None,
    new_password_salt: str | None = None,
    new_hash_iterations: int | None = None,
    new_hash_algorithm: str | None = None,
    new_login_rate_limit: int | None = None,
    session: AsyncSession | None = None,
) -> User | None:
    """Update an existing user's information."""
    stmt = (
        update(User)
        .where(User.username == username)
        .values(
            username=new_username if new_username is not None else User.username,
            password_hash=new_password_hash if new_password_hash is not None else User.password_hash,
            email=new_email if new_email is not None else User.email,
            password_salt=new_password_salt if new_password_salt is not None else User.password_salt,
            hash_iterations=new_hash_iterations if new_hash_iterations is not None else User.hash_iterations,
            hash_algorithm=new_hash_algorithm if new_hash_algorithm is not None else User.hash_algorithm,
            login_rate_limit=new_login_rate_limit if new_login_rate_limit is not None else User.login_rate_limit,
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