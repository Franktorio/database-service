# ~/src/models/crud/system/user_crud.py

from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import SessionLocal
from src.models.crud.system.auth_cookie_crud import delete_auth_cookies_by_username
from src.models.tables.system.user_table import User
from src.services.logging import log_message

PRINT_PREFIX = "USER CRUD"

async def add_user(
    username: str,
    password_hash: str,
    email: str = "",
    role: str = "user",
    password_salt: str = "",
    hash_iterations: int = 210000,
    hash_algorithm: str = "pbkdf2_sha256",
    login_rate_limit: int = 10,
    session: AsyncSession | None = None,
) -> User:
    """Add a new user to the database."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Adding user {username} with role {role}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    user = User(
        username=username,
        password_hash=password_hash,
        password_salt=password_salt,
        hash_iterations=hash_iterations,
        hash_algorithm=hash_algorithm,
        login_rate_limit=login_rate_limit,
        email=email,
        role=role,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    log_message(f"[INFO] [{PRINT_PREFIX}] User row created with id {user.id}.")

    if close_session:
        await session.close()

    return user

async def get_users(session: AsyncSession | None = None) -> list[User]:
    """Fetch all users."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Fetching all users.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(User).order_by(User.username)
    result = await session.execute(stmt)
    users = result.scalars().all()
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Retrieved {len(users)} user rows.")

    if close_session:
        await session.close()

    return users

async def get_user_by_username(username: str, session: AsyncSession | None = None) -> User | None:
    """Fetch a user by their username."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Fetching user by username: {username}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found: {username}.")

    if close_session:
        await session.close()

    return user
    
async def update_user(
    username: str,
    new_email: str | None = None,
    new_role: str | None = None,
    session: AsyncSession | None = None,
) -> User | None:
    """Update a user's email and/or role."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Updating user {username}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found for update: {username}.")
        if close_session:
            await session.close()
        return None
    await delete_auth_cookies_by_username(username, session=session)
    if new_email is not None:
        user.email = new_email
    if new_role is not None:
        user.role = new_role

    await session.commit()
    await session.refresh(user)
    log_message(f"[INFO] [{PRINT_PREFIX}] Updated user {username}.")

    if close_session:
        await session.close()

    return user

async def delete_user(username: str, session: AsyncSession | None = None) -> bool:
    """Delete a user by their username."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Deleting user {username}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    await delete_auth_cookies_by_username(username, session=session)
    stmt = delete(User).where(User.username == username)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount > 0
    if deleted:
        log_message(f"[INFO] [{PRINT_PREFIX}] Deleted user {username}.")
    else:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No user found to delete: {username}.")

    if close_session:
        await session.close()

    return deleted


async def update_user_password(
    username: str,
    new_password_hash: str,
    new_password_salt: str,
    new_hash_iterations: int = 210000,
    new_hash_algorithm: str = "pbkdf2_sha256",
    session: AsyncSession | None = None,
) -> User | None:
    """Update a user's password hash metadata."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Updating password for user {username}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found for password update: {username}.")
        if close_session:
            await session.close()
        return None
    # Delete all auth cookies for the user before updating the password
    await delete_auth_cookies_by_username(username, session=session)
    user.password_hash = new_password_hash
    user.password_salt = new_password_salt
    user.hash_iterations = new_hash_iterations
    user.hash_algorithm = new_hash_algorithm

    await session.commit()
    await session.refresh(user)
    log_message(f"[INFO] [{PRINT_PREFIX}] Updated password metadata for user {username}.")

    if close_session:
        await session.close()

    return user


async def update_user_login_rate_limit(
    username: str,
    new_login_rate_limit: int,
    session: AsyncSession | None = None,
) -> User | None:
    """Update a user's login rate limit."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Updating login rate limit for user {username}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(User).where(User.username == username)
    result = await session.execute(stmt)
    user = result.scalar_one_or_none()
    if user is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] User not found for login limit update: {username}.")
        if close_session:
            await session.close()
        return None

    user.login_rate_limit = new_login_rate_limit
    await session.commit()
    await session.refresh(user)
    log_message(f"[INFO] [{PRINT_PREFIX}] Updated login rate limit for user {username}.")

    if close_session:
        await session.close()

    return user
