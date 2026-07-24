# ~/src/services/system/cache/redis/client.py

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError

from config.loader import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
from src.services.system.logging import log_message


_client = redis.Redis(
    host=REDIS_HOST,
    port=REDIS_PORT,
    password=REDIS_PASSWORD,
    decode_responses=True,
)


class RedisClient:
    """
    Redis client for interacting with the Redis server asynchronously.
    It's a static class that provides methods to set, get, delete, and check existence of keys in Redis.
    It also provides a method to ping the Redis server to check its availability.
    """

    @staticmethod
    async def set(key: str, value: str, ex: int | None = None) -> None:
        """Set a value in Redis with an optional expiration time."""
        try:
            await _client.set(key, value, ex=ex)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def get(key: str) -> str | None:
        """Get a value from Redis. Returns None if the key does not exist."""
        try:
            return await _client.get(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def delete(key: str) -> None:
        """Delete a value from Redis."""
        try:
            await _client.delete(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def exists(key: str) -> bool:
        """Check if a key exists in Redis."""
        try:
            return await _client.exists(key) > 0
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def ping() -> bool:
        """Return True if Redis is reachable and responding to PING."""
        try:
            return bool(await _client.ping())
        except Exception as exc:
            log_message(f"[WARNING] [REDIS CLIENT] Redis ping failed: {exc}")
            return False

    @staticmethod
    async def eval(
        script: str,
        keys: list[str] | None = None,
        args: list[str | int | float | None] | None = None,
    ):
        """Execute a Lua script in Redis."""
        redis_keys = keys or []
        redis_args = ["" if value is None else str(value) for value in (args or [])]
        try:
            return await _client.eval(script, len(redis_keys), *redis_keys, *redis_args)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
        
    @staticmethod
    async def hset(key: str, ex: int | None = None, **kwargs) -> None:
        """Set multiple hash fields in Redis."""
        try:
            await _client.hset(key, mapping=kwargs)
            if ex is not None:
                await _client.expire(key, ex)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def close() -> None:
        """Close the Redis client and connection pool."""
        await _client.aclose()
        
class RateLimitServiceUnavailable(RuntimeError):
    """Raised when Redis is unavailable for rate-limit operations."""

class PermissionServiceUnavailable(RuntimeError):
    """Raised when Redis is unavailable for permission operations."""