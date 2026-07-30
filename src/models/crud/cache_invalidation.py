# ~/src/models/crud/cache_invalidation.py
# Shared write-path cache invalidation helpers for the CRUD layer.
#
# Redis key prefixes are sourced from config/service_config.json:redis_index_prefixes
# (validated via config/settings.py:RedisIndexPrefixes) so the domain prefixes
# used to build cache identifiers live in one configurable place rather than
# being hardcoded as string literals in every CRUD file.

from functools import wraps

from config.settings import REDIS_INDEX_PREFIXES
from src.services.system.cache.permissionscache import remove_cached_permission_json
from src.services.system.cache.ratelimitcache import remove_cached_rate_limit

PRINT_PREFIX = "CACHE INVALIDATION"

API_KEY_PREFIX: str = REDIS_INDEX_PREFIXES.api_key
COOKIE_PREFIX: str = REDIS_INDEX_PREFIXES.cookie
USER_PREFIX: str = REDIS_INDEX_PREFIXES.user
PASSWORD_PREFIX: str = REDIS_INDEX_PREFIXES.password
IP_BLOCK_PREFIX: str = REDIS_INDEX_PREFIXES.ip_block


def user_identifier(username: str) -> str:
    return f"{USER_PREFIX}{username}"


def api_key_identifier(key_hash: str) -> str:
    return f"{API_KEY_PREFIX}{key_hash}"


def cookie_identifier(token_hash: str) -> str:
    return f"{COOKIE_PREFIX}{token_hash}"


def password_identifier(username: str) -> str:
    return f"{PASSWORD_PREFIX}{username}"


def ip_block_identifier(ip_address: str) -> str:
    return f"{IP_BLOCK_PREFIX}{ip_address}"


async def invalidate_user_permission_cache(username: str) -> None:
    """Invalidate only the cached user permission/role payload."""
    await remove_cached_permission_json(user_identifier(username))


async def invalidate_password_ratelimit_cache(username: str) -> None:
    """Invalidate only the cached per-username login rate-limit state."""
    await remove_cached_rate_limit(password_identifier(username))


async def invalidate_api_key_ratelimit_cache(key_hash: str) -> None:
    """Invalidate only the cached per-API-key rate-limit state."""
    await remove_cached_rate_limit(api_key_identifier(key_hash))


async def invalidate_api_key_permission_cache(key_hash: str) -> None:
    """Invalidate only the cached API key permission payload."""
    await remove_cached_permission_json(api_key_identifier(key_hash))
    

async def invalidate_cookie_permission_cache(token_hash: str) -> None:
    """Invalidate only the cached per-cookie permission payload."""
    await remove_cached_permission_json(cookie_identifier(token_hash))


async def invalidate_cookie_ratelimit_cache(token_hash: str) -> None:
    """Invalidate only the cached per-cookie rate-limit state."""
    await remove_cached_rate_limit(cookie_identifier(token_hash))


async def invalidate_user_cache(username: str) -> None:
    """Invalidate a user's cached permission payload and login rate-limit state.

    Use this after any write that changes a user's own record (roles, email,
    password, login rate limit) - anything that could make the cached
    permission payload or login throttling state stale.
    """
    await invalidate_user_permission_cache(username)
    await invalidate_password_ratelimit_cache(username)


async def invalidate_api_key_cache(key_hash: str) -> None:
    """Invalidate an API key's cached rate-limit state and permission payload."""
    await invalidate_api_key_ratelimit_cache(key_hash)
    await invalidate_api_key_permission_cache(key_hash)


async def invalidate_cookie_cache(token_hash: str) -> None:
    """Invalidate an auth cookie's cached rate-limit state and permission payload."""
    await invalidate_cookie_ratelimit_cache(token_hash)
    await invalidate_cookie_permission_cache(token_hash)


def cache_invalidating(invalidator):
    """Decorator factory: runs `await invalidator(result, *args, **kwargs)`
    after the wrapped async CRUD function returns successfully.

    `invalidator` decides what to invalidate and how, based on the wrapped
    function's return value and/or call arguments. This is the single shared
    implementation used by every CRUD module that needs write-path cache
    invalidation.

    Example:
        async def _invalidate_after_write(result, *args, **kwargs) -> None:
            if isinstance(result, SomeModel):
                await invalidate_user_cache(result.username)

        @cache_invalidating(_invalidate_after_write)
        @with_session
        async def add_something(...): ...
    """
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            result = await func(*args, **kwargs)
            await invalidator(result, *args, **kwargs)
            return result
        return wrapper
    return decorator
