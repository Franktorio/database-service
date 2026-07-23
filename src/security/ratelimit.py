# ~/src/security/ratelimit.py

import time

from redis.exceptions import RedisError

from config.loader import RATE_LIMIT_WINDOW_SECONDS
from src.services.system.cache.redis.client import RedisClient


class RateLimitServiceUnavailable(RuntimeError):
    """Raised when Redis is unavailable for rate-limit operations."""


