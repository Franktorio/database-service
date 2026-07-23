# ~/src/services/system/cache/redis/client.py

import threading

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, RedisError

from config.loader import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
from src.services.system.logging import log_message


_thread_local = threading.local()


def _get_client() -> redis.Redis:
    """Return the thread-local Redis client, creating it on first access."""
    if not hasattr(_thread_local, "client"):
        _thread_local.client = redis.Redis(
            host=REDIS_HOST,
            port=REDIS_PORT,
            password=REDIS_PASSWORD,
            decode_responses=True,
        )
    return _thread_local.client


class RedisClient:
    """
    Redis client for interacting with the Redis server asynchronously.
    """
    
    @staticmethod
    async def set(key: str, value: str, expire: int = None) -> None:
        """Set a value in Redis with an optional expiration time."""
        client = _get_client()
        try:
            await client.set(key, value, ex=expire)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
    
    @staticmethod
    async def get(key: str) -> str | None:
        """Get a value from Redis. Returns None if the key does not exist."""
        client = _get_client()
        try:
            return await client.get(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
    
    @staticmethod
    async def delete(key: str) -> None:
        """Delete a value from Redis."""
        client = _get_client()
        try:
            await client.delete(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def exists(key: str) -> bool:
        """Check if a key exists in Redis."""
        client = _get_client()
        try:
            return await client.exists(key) > 0
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc

    @staticmethod
    async def ping() -> bool:
        """Return True if Redis is reachable and responding to PING."""
        client = _get_client()
        try:
            return bool(await client.ping())
        except Exception as exc:
            log_message(f"[WARNING] [REDIS CLIENT] Redis ping failed: {exc}")
            return False
