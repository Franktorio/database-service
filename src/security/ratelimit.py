import time

from redis.exceptions import RedisError

from config.loader import RATE_LIMIT_WINDOW_SECONDS
from src.services.system.cache.redis.client import RedisClient


class RateLimitServiceUnavailable(RuntimeError):
    """Raised when Redis is unavailable for rate-limit operations."""


class RateLimit:
    def __init__(self, limit: int, key_hash: str = "", permission_level: int = 0):
        self.limit = max(1, int(limit))
        self.requests = 0
        self.last_refresh_time = time.time()
        self.per_sec_refill = self.limit / max(1, RATE_LIMIT_WINDOW_SECONDS)
        self.key_hash = key_hash
        self.permission_level = permission_level
        self.redis_key = f"ratelimit:{key_hash}"

    async def _put_in_redis(self, requests: float, last_refresh_time: float) -> None:
        """Store limiter state in Redis as CSV: requests,last_refresh_time,permission_level."""
        payload = f"{requests},{last_refresh_time},{self.permission_level}"
        try:
            await RedisClient.set(
                self.redis_key,
                payload,
                expire=max(1, RATE_LIMIT_WINDOW_SECONDS),
            )
        except RedisError as exc:
            raise RateLimitServiceUnavailable("Redis unavailable for rate limiting") from exc

    async def is_allowed(self) -> tuple[bool, float]:
        """Check limiter using Redis CSV state and return (allowed, remaining_or_retry_after)."""
        now = time.time()
        try:
            raw = await RedisClient.get(self.redis_key)
        except RedisError as exc:
            raise RateLimitServiceUnavailable("Redis unavailable for rate limiting") from exc

        if raw:
            try:
                requests, previous_refresh, permission_level = map(float, raw.split(","))
                self.permission_level = int(permission_level)
            except (TypeError, ValueError):
                requests = 0.0
                previous_refresh = now
        else:
            requests = 0.0
            previous_refresh = now

        elapsed_time = max(0.0, now - previous_refresh)
        requests = max(0.0, requests - (elapsed_time * self.per_sec_refill))
        self.last_refresh_time = now

        if requests < self.limit:
            requests += 1.0
            self.requests = int(requests)
            await self._put_in_redis(requests=requests, last_refresh_time=now)
            remaining = max(0, self.limit - int(requests))
            return True, remaining

        self.requests = int(requests)
        await self._put_in_redis(requests=requests, last_refresh_time=now)
        missing_capacity = (requests - self.limit) + 1.0
        retry_after = max(0.0, missing_capacity / self.per_sec_refill)
        return False, retry_after

    async def how_long_ago(self) -> float:
        """Return seconds since last refresh in local limiter state."""
        return max(0.0, time.time() - self.last_refresh_time)
