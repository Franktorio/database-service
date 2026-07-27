# ~/src/models/crud/api_key_crud.py

from sqlalchemy import select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from functools import wraps
from src.models.database import with_session
from src.models.tables.system.api_key_table import ApiKey
from src.services.system.cache.permissionscache import remove_cached_permission_json
from src.services.system.cache.ratelimitcache import remove_from_redis
from src.services.system.logging import log_message

PRINT_PREFIX = "API KEY CRUD"


async def _invalidate_api_key_cache(key_hash: str) -> None:
    await remove_from_redis(f"api_key:{key_hash}")
    await remove_cached_permission_json(f"api_key:{key_hash}")
    
def cache_invalidating(func):
    """Decorator to invalidate cache after API key operations."""
    @wraps(func)
    async def wrapper(*args, **kwargs):
        result = await func(*args, **kwargs)
        if isinstance(result, ApiKey):
            await _invalidate_api_key_cache(result.key_hash)
        elif result is True:
            key_hash = kwargs.get("key_hash")
            if key_hash is None and args:
                key_hash = args[0]
            if isinstance(key_hash, str):
                await _invalidate_api_key_cache(key_hash)
        return result
    return wrapper

@cache_invalidating
@with_session
async def add_api_key(
    key_hash: str,
    permission_level: int = 0,
    rate_limit: int = 1000,
    email: str = "",
    session: AsyncSession | None = None,
) -> ApiKey:
    """Add a new API key to the database."""
    api_key = ApiKey(key_hash=key_hash, permission_level=permission_level, rate_limit=rate_limit, email=email)
    session.add(api_key)
    await session.commit()
    await session.refresh(api_key)

    return api_key

@with_session
async def get_api_key(key_hash: str, session: AsyncSession | None = None) -> ApiKey | None:
    """Fetch an API key by its hash."""
    stmt = select(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    api_key = result.scalar_one_or_none()
    if api_key is None:
        log_message(f"[WARNING] [{PRINT_PREFIX}] API key not found for provided hash.")

    return api_key


@with_session
async def get_api_keys(session: AsyncSession | None = None) -> list[ApiKey]:
    """Fetch all API keys."""
    stmt = select(ApiKey).order_by(ApiKey.created_at)
    result = await session.execute(stmt)
    api_keys = result.scalars().all()

    return api_keys

@cache_invalidating
@with_session
async def delete_api_key(key_hash: str, session: AsyncSession | None = None) -> bool:
    """Delete an API key by its hash."""
    stmt = delete(ApiKey).where(ApiKey.key_hash == key_hash)
    result = await session.execute(stmt)
    await session.commit()
    deleted = result.rowcount > 0
    if not deleted:
        log_message(f"[WARNING] [{PRINT_PREFIX}] No API key found to delete for provided hash.")

    return deleted


@cache_invalidating
@with_session
async def update_api_key(
    key_hash: str,
    new_permission_level: int | None = None,
    new_rate_limit: int | None = None,
    new_email: str | None = None,
    session: AsyncSession | None = None,
) -> ApiKey | None:
    """Update the permission level, rate limit, and/or email of an API key."""
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

    return updated_api_key
