# ~/src/security/tokens.py
# Generates and validates API keys, password hashes, and JWT auth cookies.

import secrets
import hashlib
import hmac
import base64
import json
from datetime import datetime, timedelta, timezone

from config.loader import (
    API_KEY_PEPPER,
    API_KEY_TOKEN_BYTES,
    JWT_ALGORITHM,
    JWT_COOKIE_NAME,
    JWT_EXP_MINUTES,
    JWT_SECRET,
    PASSWORD_HASH_ALGORITHM,
    PASSWORD_HASH_ITERATIONS,
    PASSWORD_PEPPER,
)
from src.models.crud.api_key_crud import add_api_key, get_api_key
from src.models.crud.auth_cookie_crud import add_auth_cookie
from src.services.logging import log_message


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(f"{data}{padding}".encode("ascii"))


def _jwt_sign(message: bytes) -> str:
    signature = hmac.new(JWT_SECRET.encode("utf-8"), message, hashlib.sha256).digest()
    return _b64url_encode(signature)

def generate_token() -> str:
    """Generate a new API key token."""
    log_message("[DEBUG] [API KEYS] Generating token.")
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


def verify_password(
    password: str,
    expected_hash: str,
    salt: str,
    iterations: int = PASSWORD_HASH_ITERATIONS,
) -> bool:
    """Verify a plaintext password against a stored hash."""
    candidate_hash, _ = hash_password(password, salt=salt, iterations=iterations)
    return hmac.compare_digest(candidate_hash, expected_hash)


def create_jwt_token(
    subject: str,
    username: str,
    permission_level: int = 0,
    expires_minutes: int = JWT_EXP_MINUTES,
) -> tuple[str, datetime]:
    """Create a signed JWT token for cookie authentication."""
    if JWT_ALGORITHM != "HS256":
        raise ValueError("Only HS256 is supported by the built-in JWT implementation.")

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=expires_minutes)
    payload = {
        "sub": subject,
        "username": username,
        "permission_level": permission_level,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }
    header = {"alg": "HS256", "typ": "JWT"}
    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
    signature_b64 = _jwt_sign(signing_input)
    token = f"{header_b64}.{payload_b64}.{signature_b64}"
    return token, expires_at


def decode_jwt_token(token: str) -> dict | None:
    """Decode and validate a JWT token payload."""
    try:
        if JWT_ALGORITHM != "HS256":
            raise ValueError("Only HS256 is supported by the built-in JWT implementation.")

        parts = token.split(".")
        if len(parts) != 3:
            return None

        header_b64, payload_b64, signature_b64 = parts
        signing_input = f"{header_b64}.{payload_b64}".encode("ascii")
        expected_signature = _jwt_sign(signing_input)
        if not hmac.compare_digest(signature_b64, expected_signature):
            return None

        header_raw = _b64url_decode(header_b64)
        payload_raw = _b64url_decode(payload_b64)
        header = json.loads(header_raw.decode("utf-8"))
        payload = json.loads(payload_raw.decode("utf-8"))

        if header.get("alg") != "HS256":
            return None

        exp = int(payload.get("exp", 0))
        if exp <= int(datetime.now(timezone.utc).timestamp()):
            return None

        return payload
    except (ValueError, TypeError, json.JSONDecodeError):
        log_message("[WARNING] [API KEYS] Invalid JWT token presented.")
        return None


async def create_cookie_token(
    subject: str,
    username: str,
    permission_level: int = 0,
    expires_minutes: int = JWT_EXP_MINUTES,
) -> str:
    """Create a JWT token and persist a hash for revocation/rate-limiting checks."""
    token, expires_at = create_jwt_token(
        subject=subject,
        username=username,
        permission_level=permission_level,
        expires_minutes=expires_minutes,
    )
    token_hash = hash_token(token)
    await add_auth_cookie(
        token_hash=token_hash,
        username=username,
        expires_at=expires_at,
    )
    return token


def get_cookie_settings(expires_minutes: int = JWT_EXP_MINUTES) -> dict:
    """Return default cookie settings for storing JWT tokens client-side."""
    max_age = expires_minutes * 60
    return {
        "key": JWT_COOKIE_NAME,
        "httponly": True,
        "secure": True,
        "samesite": "lax",
        "path": "/",
        "max_age": max_age,
    }

async def create_api_key(permission_level: int = 0, rate_limit: int = 1000, email: str = "") -> str:
    """Create a new API key and store it in the database."""
    log_message(f"[INFO] [API KEYS] Creating API key with permission level {permission_level} and rate limit {rate_limit}.")
    token = generate_token()
    token_hash = hash_token(token)
    await add_api_key(token_hash, permission_level, rate_limit, email)
    log_message("[INFO] [API KEYS] API key created successfully.")
    return token

async def validate_token(token: str) -> bool:
    """Validate an API key token against the stored hash."""
    log_message("[DEBUG] [API KEYS] Validating API key token.")
    token_hash = hash_token(token)
    api_key = await get_api_key(token_hash)
    is_valid = api_key is not None
    if not is_valid:
        log_message("[WARNING] [API KEYS] API key validation failed.")
    return is_valid
