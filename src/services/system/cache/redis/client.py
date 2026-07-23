# ~/src/services/system/cache/redis/client.py

import redis.asyncio as redis
from redis.exceptions import ConnectionError as RedisConnectionError, RedisError

from config.loader import REDIS_HOST, REDIS_PASSWORD, REDIS_PORT
from src.services.system.logging import log_message


def _new_client() -> redis.Redis:
    return redis.Redis(
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
        client = _new_client()
        try:
            await client.set(key, value, ex=expire)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
        finally:
            await client.aclose()
    
    @staticmethod
    async def get(key: str) -> str | None:
        """Get a value from Redis. Returns None if the key does not exist."""
        client = _new_client()
        try:
            return await client.get(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
        finally:
            await client.aclose()
    
    @staticmethod
    async def delete(key: str) -> None:
        """Delete a value from Redis."""
        client = _new_client()
        try:
            await client.delete(key)
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
        finally:
            await client.aclose()

    @staticmethod
    async def exists(key: str) -> bool:
        """Check if a key exists in Redis."""
        client = _new_client()
        try:
            return await client.exists(key) > 0
        except Exception as exc:
            raise RedisConnectionError(str(exc)) from exc
        finally:
            await client.aclose()

    @staticmethod
    async def ping() -> bool:
        """Return True if Redis is reachable and responding to PING."""
        client = _new_client()
        try:
            return bool(await client.ping())
        except Exception as exc:
            log_message(f"[WARNING] [REDIS CLIENT] Redis ping failed: {exc}")
            return False
        finally:
            await client.aclose()
