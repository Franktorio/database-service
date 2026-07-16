# ~/src/api/validate.py
# Decorator orchestrator for API key validation and rate limiting.

from functools import wraps

from src.models.tables.api_key_table import ApiKey
from src.models.crud.api_key_crud import get_api_key
from src.api.keys import hash_token
from src.api.ratelimit import RateLimit
from src.api.models import RequestBase
from src.api.config import PERM_LEVEL_MAP

PRINT_PREFIX = "API VALIDATE"

old_ratelimit_generation: dict[str, RateLimit] = {}  # 
current_ratelimit_generation: dict[str, RateLimit] = {}

_call_counter = 0
_CLEANUP_THRESHOLD = 1000

def _place_in_ratelimiters(api_key: ApiKey) -> RateLimit:
    """Place the API key in the rate limiters dictionary and return its RateLimit instance."""
    api_hash = api_key.key_hash
    limit = api_key.rate_limit
    level = api_key.permission_level
    current_ratelimit_generation[api_hash] = RateLimit(limit=limit, key_hash=api_hash, permission_level=level)
    print(f"[DEBUG] [{PRINT_PREFIX}] Placed API key {api_hash} in rate limiters with limit {api_key.rate_limit}.")
    return current_ratelimit_generation[api_hash]

def _cleanup_ratelimiters():
    """Clean inactive RateLimiters older than the cleanup threshold."""
    global old_ratelimit_generation, current_ratelimit_generation
    old_ratelimit_generation = current_ratelimit_generation
    current_ratelimit_generation = {}

async def _obtain_ratelimit(api_key: str) -> RateLimit | None:
    """Store the API key in the rate limiters dictionary and return its RateLimit instance."""
    global _call_counter
    
    api_hash = hash_token(api_key)
    
    _call_counter += 1
    if _call_counter >= _CLEANUP_THRESHOLD:
        _cleanup_ratelimiters()
        _call_counter = 0
    
    if api_hash in current_ratelimit_generation:
        return current_ratelimit_generation[api_hash]
    
    if api_hash in old_ratelimit_generation:
        ratelimit = old_ratelimit_generation.pop(api_hash)
        current_ratelimit_generation[api_hash] = ratelimit
        print(f"[DEBUG] [{PRINT_PREFIX}] Moved API key {api_hash} from old to current rate limiters.")
        return ratelimit
    
    database_entry = await get_api_key(api_hash)
    
    if database_entry is None:
        print(f"[WARNING] [{PRINT_PREFIX}] API key {api_key} attempting to use the API without being registered.")
        return None
    
    return _place_in_ratelimiters(database_entry)


def with_validation(permission_level: int):
    """Decorator to validate API key and enforce rate limiting."""
    def decorator(func):
        @wraps(func)
        async def wrapper(request: RequestBase, *args, **kwargs):
            api_key = request.api_key
            ratelimit = await _obtain_ratelimit(api_key)
            
            if ratelimit is None:
                print(f"[WARNING] [{PRINT_PREFIX}] API key {api_key} is not registered.")
                return {"error": "API key is not registered."}, 403
            
            if ratelimit.permission_level < permission_level:
                print(f"[WARNING] [{PRINT_PREFIX}] API key {api_key} does not have sufficient permissions. Required: {permission_level}, Found: {ratelimit.permission_level}.")
                return {"error": "Insufficient permissions."}, 403
            
            allowed, status = ratelimit.is_allowed()
            if not allowed:
                print(f"[WARNING] [{PRINT_PREFIX}] API key {api_key} has exceeded its rate limit. Time until next request allowed: {status:.2f} seconds.")
                return {"error": "Rate limit exceeded.", "retry_after": status}, 429
            
            api_data = {
                'api_key': api_key,
                'permission_level': ratelimit.permission_level,
                'permission_name': PERM_LEVEL_MAP.get(ratelimit.permission_level, "UNKNOWN"),
                'rate_limit': ratelimit.limit,
                'requests_remaining': ratelimit.limit - ratelimit.requests,
                'seconds_since_last_request': ratelimit.how_long_ago()
            }
            
            request._api_data = api_data
            
            return await func(request, *args, **kwargs)
        return wrapper
    return decorator
    