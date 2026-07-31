# ~/src/security/tokens.py
# Generates and validates API keys, password hashes, and JWT auth cookies.

import asyncio
import secrets
import hashlib
import hmac
from datetime import datetime, timedelta, timezone
import jwt
from jwt import ExpiredSignatureError, InvalidTokenError

from config.loader import (
    API_KEY_PEPPER,
    API_KEY_TOKEN_BYTES,
    JWT_ALGORITHM,
    JWT_EXP_MINUTES,
    JWT_SECRET,
    PASSWORD_HASH_ALGORITHM,
    PASSWORD_HASH_ITERATIONS,
    PASSWORD_PEPPER,
    OPERATING_MODE,
    OPERATING_MODE_PRODUCTION,
)
from src.api.config import COOKIE_JWT_INDEX
from src.models.crud.system.api_key_crud import add_api_key, get_api_key
from src.models.crud.system.auth_cookie_crud import add_auth_cookie
from src.models.crud.system.user.user_crud import get_user_by_username
from src.models.tables.system.api_key_table import ApiKey
from src.services.system.logging import log_message

def generate_token() -> str:
    """Generate a new API key token."""
    return secrets.token_urlsafe(API_KEY_TOKEN_BYTES)

def hash_token(token: str) -> str:
    """Hash the API key token for secure storage.

    A pepper improves resistance to precomputed hash attacks if DB contents leak.
    """
    return hashlib.sha256(f"{API_KEY_PEPPER}:{token}".encode()).hexdigest()


def generate_password_salt() -> str:
    """Generate a cryptographically secure salt for password hashing."""
    return secrets.token_hex(16)


def hash_password(
    password: str,
    salt: str | None = None,
    iterations: int = PASSWORD_HASH_ITERATIONS,
) -> tuple[str, str]:
    """Hash a password using PBKDF2-HMAC-SHA256 and return (hash_hex, salt)."""
    chosen_salt = salt or generate_password_salt()
    payload = f"{PASSWORD_PEPPER}:{password}".encode("utf-8")
    if PASSWORD_HASH_ALGORITHM != "pbkdf2_sha256":
        raise ValueError("Only pbkdf2_sha256 is supported.")

    derived_key = hashlib.pbkdf2_hmac(
        "sha256",
        payload,
        chosen_salt.encode("utf-8"),
        iterations,
    )
    return derived_key.hex(), chosen_salt


async def verify_password(
    password: str,
    expected_hash: str,
    salt: str,
    iterations: int = PASSWORD_HASH_ITERATIONS,
) -> bool:
    """Verify a plaintext password against a stored hash."""

    def _verify() -> bool:
        candidate_hash, _ = hash_password(
            password,
            salt=salt,
            iterations=iterations,
        )
        return hmac.compare_digest(candidate_hash, expected_hash)

    return await asyncio.to_thread(_verify)


def create_jwt_token(
    username: str,
    role: str,
    user_id: int | None = None,
    expires_minutes: int = JWT_EXP_MINUTES,
) -> tuple[str, datetime]:
    """Create a signed JWT token for cookie authentication."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_minutes)
    payload = {
        "username": username,
        "role": role,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    if user_id is not None:
        payload["user_id"] = user_id
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, expires_at


def decode_jwt_token(token: str) -> dict | None:
    """Decode and validate a JWT token payload."""
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        return payload
    except ExpiredSignatureError:
        return None
    except (InvalidTokenError, ValueError, TypeError):
        log_message("[WARNING] [API KEYS] Invalid JWT token presented.")
        return None


async def create_cookie_token(
    username: str,
    role: str,
    expires_minutes: int = JWT_EXP_MINUTES,
) -> str:
    """Create a JWT token and persist a hash for revocation/rate-limiting checks."""
    user = await get_user_by_username(username)
    if user is None:
        log_message(f"[WARNING] [API KEYS] Cannot create cookie token for unknown user {username}.")
        raise ValueError("Cannot create cookie token for unknown user.")

    token, expires_at = create_jwt_token(
        username=user.username,
        role=role,
        user_id=user.id,
        expires_minutes=expires_minutes,
    )
    token_hash = hash_token(token)
    await add_auth_cookie(
        token_hash=token_hash,
        user=user,
        expires_at=expires_at,
    )
    return token


def get_cookie_settings(expires_minutes: int = JWT_EXP_MINUTES) -> dict:
    """Return default cookie settings for storing JWT tokens client-side."""
    max_age = expires_minutes * 60
    return {
        "key": COOKIE_JWT_INDEX,
        "httponly": True,
        "secure": OPERATING_MODE == OPERATING_MODE_PRODUCTION,  # Set to True in production with HTTPS
        "samesite": "lax",
        "path": "/",
        "max_age": max_age,
    }

async def create_api_key(permission_level: int = 0, rate_limit: int = 1000, email: str = "") -> tuple[str, ApiKey]:
    """Create a new API key and store it in the database.

    Returns the raw token (shown to the caller exactly once) and the stored row
    (whose opaque `id` is the public identifier for later PATCH/DELETE calls).
    """
    token = generate_token()
    token_hash = hash_token(token)
    api_key = await add_api_key(token_hash, permission_level, rate_limit, email)
    return token, api_key

async def validate_token(token: str) -> bool:
    """Validate an API key token against the stored hash."""
    token_hash = hash_token(token)
    api_key = await get_api_key(token_hash)
    is_valid = api_key is not None
    if not is_valid:
        log_message("[WARNING] [API KEYS] API key validation failed.")
    return is_valid
