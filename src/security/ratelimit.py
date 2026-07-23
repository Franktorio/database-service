import time

from redis.exceptions import RedisError

from config.loader import RATE_LIMIT_WINDOW_SECONDS
from src.services.system.cache.redis.client import RedisClient


class RateLimitServiceUnavailable(RuntimeError):
    """Raised when Redis is unavailable for rate-limit operations."""


_TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local limit = tonumber(ARGV[1])
local refill_per_ms = tonumber(ARGV[2])
local now_ms = tonumber(ARGV[3])
local ttl_ms = tonumber(ARGV[4])
local permission_level = tonumber(ARGV[5])

local data = redis.call('GET', key)
local tokens = limit
local last_ms = now_ms
local stored_permission = permission_level

if data then
    local token_str, last_ms_str, permission_str = string.match(data, "([^,]+),([^,]+),([^,]+)")
    if token_str and last_ms_str then
        tokens = tonumber(token_str) or limit
        last_ms = tonumber(last_ms_str) or now_ms
        if permission_str then
            stored_permission = tonumber(permission_str) or permission_level
        end
    end
end

local elapsed_ms = math.max(0, now_ms - last_ms)
tokens = math.min(limit, tokens + (elapsed_ms * refill_per_ms))

local allowed = 0
local retry_after = 0
if tokens >= 1 then
    tokens = tokens - 1
    allowed = 1
else
    local missing_tokens = 1 - tokens
    retry_after = (missing_tokens / refill_per_ms) / 1000
end

redis.call('SET', key, tostring(tokens) .. "," .. tostring(now_ms) .. "," .. tostring(stored_permission), 'PX', ttl_ms)
return {allowed, retry_after, tokens, stored_permission}
"""


class RateLimit:
    def __init__(
        self,
        limit: int,
        key_hash: str = "",
        permission_level: int = 0,
        window_seconds: int = RATE_LIMIT_WINDOW_SECONDS,
    ):
        self.limit = max(1, int(limit))
        self.requests = 0
        self.last_refresh_time = time.time()
        self.window_seconds = max(1, int(window_seconds))
        self.per_sec_refill = self.limit / self.window_seconds
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
        """Check limiter using an atomic Redis token bucket and return (allowed, remaining_or_retry_after)."""
        now = time.time()
        now_ms = int(now * 1000)
        window_ms = max(1000, self.window_seconds * 1000)
        refill_per_ms = self.limit / window_ms
        try:
            result = await RedisClient.eval(
                _TOKEN_BUCKET_LUA,
                1,
                self.redis_key,
                str(self.limit),
                str(refill_per_ms),
                str(now_ms),
                str(window_ms),
                str(self.permission_level),
            )
        except RedisError as exc:
            raise RateLimitServiceUnavailable("Redis unavailable for rate limiting") from exc

        try:
            allowed = int(result[0]) == 1
            retry_after = float(result[1])
            tokens = float(result[2])
            self.permission_level = int(float(result[3]))
        except (TypeError, ValueError, IndexError) as exc:
            raise RateLimitServiceUnavailable("Redis returned invalid limiter state") from exc

        self.last_refresh_time = now
        self.requests = max(0, int(self.limit - tokens))

        if allowed:
            remaining = max(0, int(tokens))
            return True, float(remaining)
        return False, max(0.0, retry_after)

    async def how_long_ago(self) -> float:
        """Return seconds since last refresh in local limiter state."""
        return max(0.0, time.time() - self.last_refresh_time)

    async def delete(self) -> None:
        """Delete limiter state from Redis."""
        try:
            await RedisClient.delete(self.redis_key)
        except RedisError as exc:
            raise RateLimitServiceUnavailable("Redis unavailable for rate limiting") from exc