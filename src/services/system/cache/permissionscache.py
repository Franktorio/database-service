import json

from redis.exceptions import RedisError

from config.loader import PROJECT_ROOT, REDIS_PERMISSIONS_EX_SECONDS
from src.services.system.cache.redis.client import RedisClient, PermissionServiceUnavailable


try:
    with open(f"{PROJECT_ROOT}/src/services/system/cache/redis/permissions_logic.lua", "r") as f:
        LUA_SCRIPT = f.read()
except FileNotFoundError as exc:
    raise FileNotFoundError(
        "The Lua script for permissions caching was not found. Please ensure that "
        "'permissions_logic.lua' exists in 'src/services/system/cache/redis/'."
    ) from exc


def _key(identifier: str) -> str:
    return f"permissions:{identifier}"


async def cache_permission_json(
    identifier: str,
    permission_json: dict,
    ex: int | None = REDIS_PERMISSIONS_EX_SECONDS,
) -> None:
    """Cache permission metadata JSON for an identifier."""
    try:
        await RedisClient.set(
            _key(identifier),
            json.dumps(permission_json),
            ex=ex,
        )
    except RedisError as exc:
        raise PermissionServiceUnavailable(
            f"Redis error occurred while caching permissions: {exc}"
        ) from exc


async def get_cached_permission_json(identifier: str) -> dict | None:
    """Retrieve cached permission metadata JSON for an identifier."""
    try:
        stringified = await RedisClient.eval(LUA_SCRIPT, keys=[_key(identifier)], args=[])
        if stringified in (None, "NOT_FOUND"):
            return None
        return json.loads(stringified)
    except RedisError as exc:
        raise PermissionServiceUnavailable(
            f"Redis error occurred while retrieving cached permissions: {exc}"
        ) from exc


async def remove_cached_permission_json(identifier: str) -> None:
    """Remove cached permission metadata JSON for an identifier."""
    try:
        await RedisClient.delete(_key(identifier))
    except RedisError as exc:
        raise PermissionServiceUnavailable(
            f"Redis error occurred while removing cached permissions: {exc}"
        ) from exc
