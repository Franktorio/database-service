# ~/src/api/ratelimit.py

import time

PRINT_PREFIX = "RATE LIMIT"

_MINUTE_SECS = 60

class RateLimit:
    def __init__(self, limit: int, key_hash: str = "", permission_level: int = 0):
        self.limit = limit
        self.requests = 0
        self.last_refresh_time = time.time()
        self.per_sec_refill = limit / _MINUTE_SECS
        self.key_hash = key_hash
        self.permission_level = permission_level
    
    def is_allowed(self) -> tuple[bool, float]:
        """
        Check if a request is allowed under the rate limit.
        
        Returns:
            tuple[bool, float]:
             - If true, returns the remaining requests allowed in the current minute.
             - If false, returns the time in seconds until the next request is allowed.
        """
        current_time = time.time()
        elapsed_time = current_time - self.last_refresh_time
        
        # Refill the requests based on elapsed time
        refill_amount = elapsed_time * self.per_sec_refill
        self.requests = max(0, self.requests - refill_amount)
        self.last_refresh_time = current_time
        
        if self.requests < self.limit:
            self.requests += 1
            return True, self.limit - self.requests
        else:
            print(f"[WARNING] [{PRINT_PREFIX}] Rate limit exceeded for key {self.key_hash}. Current requests: {self.requests}, Limit: {self.limit}.")
            return False, 1 / self.per_sec_refill  # Estimated time until next request is allowed
        
    def how_long_ago(self) -> float:
        """Return the time in seconds since the last refresh."""
        return time.time() - self.last_refresh_time