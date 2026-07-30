import time
from typing import Literal

from redis.exceptions import RedisError

from config.loader import PROJECT_ROOT, RATE_LIMIT_WINDOW_SECONDS, REDIS_RATELIMIT_EX_SECONDS
from src.services.system.monitoring import monitored
from src.services.system.cache.redis.client import RedisClient, RateLimitServiceUnavailable


try:
    with open(f"{PROJECT_ROOT}/src/services/system/cache/redis/ratelimit_logic.lua", "r") as f:
        LUA_SCRIPT = f.read()
except FileNotFoundError as exc:
    raise FileNotFoundError(
        "The Lua script for rate limiting was not found. Please ensure that "
        "'ratelimit_logic.lua' exists in 'src/services/system/cache/redis/'."
    ) from exc


def _key(identifier: str) -> str:
    return f"ratelimit:{identifier}"

@monitored(measuring="redis", operation_type="read")
async def process_cached_rate_limit(
    identifier: str,
    too_soon_window_seconds: int | None = None,
) -> Literal["ALLOWED", "DENIED", "TOO_SOON", "NOT_FOUND", "INVALID_DATA"]:
    """Check if a request is allowed based on cached Redis rate-limit data."""
    try:
        current_time = int(time.time())
        result = await RedisClient.eval(
            LUA_SCRIPT,
            keys=[_key(identifier)],
            args=[current_time, too_soon_window_seconds],
        )
        return result
    except RedisError as exc:
        raise RateLimitServiceUnavailable(
            f"Redis error occurred while checking rate limit: {exc}"
        ) from exc

@monitored(measuring="redis", operation_type="write")
async def cache_rate_limit(
    identifier: str,
    limit: int,
    window: int | None = RATE_LIMIT_WINDOW_SECONDS,
    ex: int | None = REDIS_RATELIMIT_EX_SECONDS,
) -> bool:
    """Store rate-limit metadata for an identifier in Redis."""
    try:
        await RedisClient.hset(
            _key(identifier),
            ex=ex,
            requests=0,
            limit=limit,
            window=window,
            last_request_time=time.time(),
        )
        return True
    except RedisError as exc:
        raise RateLimitServiceUnavailable(
            f"Redis error occurred while placing rate limit information: {exc}"
        ) from exc

@monitored(measuring="redis", operation_type="write")
async def remove_cached_rate_limit(identifier: str) -> bool:
    """Remove rate-limit metadata from Redis for an identifier."""
    try:
        await RedisClient.delete(_key(identifier))
        return True
    except RedisError as exc:
        raise RateLimitServiceUnavailable(
            f"Redis error occurred while removing rate limit information: {exc}"
        ) from exc
