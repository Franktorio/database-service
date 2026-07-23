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
    """

    @staticmethod
    async def set(key: str, value: str, expire: int = None) -> None:
        """Set a value in Redis with an optional expiration time."""
        try:
            await _client.set(key, value, ex=expire)
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
    async def eval(script: str, numkeys: int, *keys_and_args: str):
        """Execute a Lua script in Redis."""
        try:
            return await _client.eval(script, numkeys, *keys_and_args)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def close() -> None:
        """Close the Redis client and connection pool."""
        await _client.aclose()