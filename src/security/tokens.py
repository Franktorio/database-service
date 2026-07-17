# ~/src/security/tokens.py
# Generates, stores and manages API keys for the application.

import secrets
import hashlib

from config.loader import API_KEY_PEPPER
from src.models.crud.api_key_crud import add_api_key, get_api_key
from src.services.logging import log_message

PRINT_PREFIX = "API KEYS"

KEY_LENGTH = 64  # Length of the generated API key token in bytes

def generate_token() -> str:
    """Generate a new API key token."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Generating token.")
    return secrets.token_urlsafe(KEY_LENGTH)

def hash_token(token: str) -> str:
    """Hash the API key token for secure storage.

    A pepper improves resistance to precomputed hash attacks if DB contents leak.
    """
    return hashlib.sha256(f"{API_KEY_PEPPER}:{token}".encode()).hexdigest()

async def create_api_key(permission_level: int = 0, rate_limit: int = 1000, email: str = "") -> str:
    """Create a new API key and store it in the database."""
    log_message(f"[INFO] [{PRINT_PREFIX}] Creating API key with permission level {permission_level} and rate limit {rate_limit}.")
    token = generate_token()
    token_hash = hash_token(token)
    await add_api_key(token_hash, permission_level, rate_limit, email)
    log_message(f"[INFO] [{PRINT_PREFIX}] API key created successfully.")
    return token

async def validate_token(token: str) -> bool:
    """Validate an API key token against the stored hash."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Validating API key token.")
    token_hash = hash_token(token)
    api_key = await get_api_key(token_hash)
    is_valid = api_key is not None
    if not is_valid:
        log_message(f"[WARNING] [{PRINT_PREFIX}] API key validation failed.")
    return is_valid
