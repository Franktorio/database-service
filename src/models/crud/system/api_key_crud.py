# ~/src/models/crud/api_key_crud.py

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from src.models.database import SessionLocal
from src.models.tables.system.api_key_table import ApiKey
from src.services.system.cache.permissionscache import remove_cached_permission_json
from src.services.system.cache.ratelimitcache import remove_from_redis
from src.services.system.logging import log_message

PRINT_PREFIX = "API KEY CRUD"


async def _invalidate_api_key_cache(key_hash: str) -> None:
    await remove_from_redis(f"api_key:{key_hash}")
    await remove_cached_permission_json(f"api_key:{key_hash}")

async def add_api_key(
    key_hash: str,
    permission_level: int = 0,
    rate_limit: int = 1000,
    email: str = "",
    session: AsyncSession | None = None,
) -> ApiKey:
    """Add a new API key to the database."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Adding API key with permission level {permission_level} and rate limit {rate_limit} to email {email}.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    api_key = ApiKey(key_hash=key_hash, permission_level=permission_level, rate_limit=rate_limit, email=email)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)
    await _invalidate_api_key_cache(key_hash)
    log_message(f"[INFO] [{PRINT_PREFIX}] API key row created with id {api_key.id}.")

    if close_session:
        await session.close()

    return api_key
    
async def get_api_key(key_hash: str, session: AsyncSession | None = None) -> ApiKey | None:
    """Fetch an API key by its hash."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Fetching API key by hash.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    api_key = result.scalar_one_or_none()
    if api_key is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] API key not found for provided hash.")

    if close_session:
        await session.close()

    return api_key
    
async def get_api_keys(session: AsyncSession | None = None) -> list[ApiKey]:
    """Fetch all API keys."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = select(ApiKey).order_by(ApiKey.created_at)
    result = await session.execute(stmt)
    api_keys = result.scalars().all()
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Retrieved {len(api_keys)} API key rows.")

    if close_session:
        await session.close()

    return api_keys
    
async def delete_api_key(key_hash: str, session: AsyncSession | None = None) -> bool:
    """Delete an API key by its hash."""
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = delete(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount > 0
    if deleted:
        await _invalidate_api_key_cache(key_hash)
    if deleted:
        log_message(f"[INFO] [{PRINT_PREFIX}] Deleted API key for provided hash.")
    else:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No API key found to delete for provided hash.")

    if close_session:
        await session.close()

    return deleted
    
async def update_api_key(
    key_hash: str,
    new_permission_level: int | None = None,
    new_rate_limit: int | None = None,
    new_email: str | None = None,
    session: AsyncSession | None = None,
) -> ApiKey | None:
    """Update the permission level, rate limit, and/or email of an API key."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Updating API key attributes.")
    close_session = False
    if session is None:
        session = SessionLocal()
        close_session = True

    stmt = (
        update(ApiKey)
        .where(ApiKey.key_hash == key_hash)
        .values(
            permission_level=new_permission_level if new_permission_level is not None else ApiKey.permission_level,
            rate_limit=new_rate_limit if new_rate_limit is not None else ApiKey.rate_limit,
            email=new_email if new_email is not None else ApiKey.email,
        )
        .returning(ApiKey)
    )
    result = await session.execute(stmt)
    await session.commit()
    updated_api_key = result.scalar_one_or_none()
    if updated_api_key is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] API key update skipped; key not found.")
    else:
        await _invalidate_api_key_cache(key_hash)
        log_message(f"[INFO] [{PRINT_PREFIX}] Updated API key id {updated_api_key.id}.")

    if close_session:
        await session.close()

    return updated_api_key
