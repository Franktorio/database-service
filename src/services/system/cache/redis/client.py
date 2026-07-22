# ~/src/services/system/cache/redis/client.py

import redis.asyncio as redis
from redis.exceptions import RedisError

from config.loader import REDIS_HOST, REDIS_PORT, REDIS_PASSWORD
from src.services.system.logging import log_message

redis_server = redis.Redis(
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
        await redis_server.set(key, value, ex=expire)
    
    @staticmethod
    async def get(key: str) -> str | None:
        """Get a value from Redis. Returns None if the key does not exist."""
        return await redis_server.get(key)
    
    @staticmethod
    async def delete(key: str) -> None:
        """Delete a value from Redis."""
        await redis_server.delete(key)

    @staticmethod
    async def exists(key: str) -> bool:
        """Check if a key exists in Redis."""
        return await redis_server.exists(key) > 0

    @staticmethod
    async def ping() -> bool:
        """Return True if Redis is reachable and responding to PING."""
        try:
            return bool(await redis_server.ping())
        except RedisError as exc:
            log_message(f"[ERROR] [REDIS CLIENT] Redis ping failed: {exc}")
            return False
