# ~/config/loader.py
# This file is responsible for loading environment variables from a .env file.

import dotenv
import logging
import os
from pathlib import Path

PRINT_PREFIX = "CONFIG LOADER"
logger = logging.getLogger("database_service")

# Load environment variables from .env file
_env_file = os.getenv('ENV_FILE', '.env')
CONFIG_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = CONFIG_DIR.parent
_env_path = CONFIG_DIR / _env_file
dotenv.load_dotenv(str(_env_path))

OPERATING_MODE: str = os.getenv('OPERATING_MODE', 'development')

# PostgreSQL database configuration
POSTGRESQL_DATABASE_NAME: str = os.getenv('POSTGRESQL_DATABASE_NAME', 'mydatabase')
POSTGRESQL_USERNAME: str = os.getenv('POSTGRESQL_USERNAME', 'postgres')
POSTGRESQL_PASSWORD: str = os.getenv('POSTGRESQL_PASSWORD', 'your_password')
POSTGRESQL_HOST: str = os.getenv('POSTGRESQL_HOST', 'localhost')
POSTGRESQL_PORT: str = os.getenv('POSTGRESQL_PORT', '5432')

# SQLAlchemy database URL for asynchronous PostgreSQL connection
DATABASE_URL = (
    f"postgresql+asyncpg://{POSTGRESQL_USERNAME}:{POSTGRESQL_PASSWORD}@{POSTGRESQL_HOST}:{POSTGRESQL_PORT}/{POSTGRESQL_DATABASE_NAME}"
)

# Pool configuration
POSTGRESQL_POOL_SIZE: int = int(os.getenv('POSTGRESQL_POOL_SIZE', '10'))
POSTGRESQL_POOL_MAX_OVERFLOW: int = int(os.getenv('POSTGRESQL_POOL_MAX_OVERFLOW', '20'))
POSTGRESQL_POOL_TIMEOUT_SECONDS: int = int(os.getenv('POSTGRESQL_POOL_TIMEOUT_SECONDS', '30'))
POSTGRESQL_POOL_RECYCLE_SECONDS: int = int(os.getenv('POSTGRESQL_POOL_RECYCLE_SECONDS', '1800'))
POSTGRESQL_POOL_PRE_PING: bool = os.getenv('POSTGRESQL_POOL_PRE_PING', 'true').lower() in ('true', '1', 't')

# API server configuration
API_ENABLED: bool = os.getenv('API_ENABLED', 'True').lower() in ('true', '1', 't')
API_PORT: int = int(os.getenv('API_PORT', '8000'))
API_KEY_PEPPER: str = os.getenv('API_KEY_PEPPER', 'dev-only-change-me')
PASSWORD_PEPPER: str = os.getenv('PASSWORD_PEPPER', 'dev-only-change-me-password')
JWT_SECRET: str = os.getenv('JWT_SECRET', 'dev-only-change-me-jwt')
JWT_ALGORITHM: str = os.getenv('JWT_ALGORITHM', 'HS256')
JWT_EXP_MINUTES: int = int(os.getenv('JWT_EXP_MINUTES', '60'))
API_KEY_TOKEN_BYTES: int = int(os.getenv('API_KEY_TOKEN_BYTES', '64'))
PASSWORD_HASH_ITERATIONS: int = int(os.getenv('PASSWORD_HASH_ITERATIONS', '210000'))
PASSWORD_HASH_ALGORITHM: str = os.getenv('PASSWORD_HASH_ALGORITHM', 'pbkdf2_sha256')
LOGIN_ATTEMPTS_LIMIT: int = int(os.getenv('LOGIN_ATTEMPTS_LIMIT', '10'))
LOGIN_TIME_WINDOW: int = int(os.getenv('LOGIN_TIME_WINDOW', '1800'))
COOKIE_DEFAULT_RATE_LIMIT: int = int(os.getenv('COOKIE_DEFAULT_RATE_LIMIT', '120'))
RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv('RATE_LIMIT_WINDOW_SECONDS', '60'))

# IP Blocking configuration
IP_BLOCKING_ENABLED: bool = os.getenv('IP_BLOCKING_ENABLED', 'true').lower() in ('true', '1', 't')
IP_BLOCKING_THRESHOLD: int = int(os.getenv('IP_BLOCKING_THRESHOLD', '300'))
IP_BLOCKING_TIME_WINDOW: int = int(os.getenv('IP_BLOCKING_TIME_WINDOW', '10'))
IP_BLOCKING_DURATION: int = int(os.getenv('IP_BLOCKING_DURATION', '3600'))

TRUSTED_PROXIES: list[str] = [proxy.strip() for proxy in os.getenv('TRUSTED_PROXIES', '').split(',') if proxy.strip()]

# Redis configuration
REDIS_HOST: str = os.getenv('REDIS_HOST', 'localhost')
REDIS_PORT: int = int(os.getenv('REDIS_PORT', '6379'))
REDIS_PASSWORD: str = os.getenv('REDIS_PASSWORD', 'change-me-before-production')
REDIS_RATELIMIT_EX_SECONDS: int = int(os.getenv('REDIS_RATELIMIT_EX_SECONDS', '3600'))
REDIS_PERMISSIONS_EX_SECONDS: int = int(os.getenv('REDIS_PERMISSIONS_EX_SECONDS', '300'))
REDIS_IP_BLOCK_EX_SECONDS: int = int(os.getenv('REDIS_IP_BLOCK_EX_SECONDS', '3600'))

def _is_unsafe_secret(value: str, known_default: str) -> bool:
    if not value:
        return True
    if value == known_default:
        return True
    return False


def _enforce_secret_safety() -> None:
    unsafe_password = _is_unsafe_secret(POSTGRESQL_PASSWORD, 'your_password')
    unsafe_pepper = _is_unsafe_secret(API_KEY_PEPPER, 'dev-only-change-me')
    unsafe_password_pepper = _is_unsafe_secret(PASSWORD_PEPPER, 'dev-only-change-me-password')
    unsafe_jwt_secret = _is_unsafe_secret(JWT_SECRET, 'dev-only-change-me-jwt')
    unsafe_redis_password = _is_unsafe_secret(os.getenv('REDIS_PASSWORD', ''), 'change-me-before-production')

    if OPERATING_MODE != 'development':
        if unsafe_password:
            raise RuntimeError(
                "POSTGRESQL_PASSWORD is not securely configured. "
                "Set a strong secret in config/.env for non-development mode."
            )
        if unsafe_pepper:
            raise RuntimeError(
                "API_KEY_PEPPER is not securely configured. "
                "Set a strong secret in config/.env for non-development mode."
            )
        if unsafe_password_pepper:
            raise RuntimeError(
                "PASSWORD_PEPPER is not securely configured. "
                "Set a strong secret in config/.env for non-development mode."
            )
        if unsafe_jwt_secret:
            raise RuntimeError(
                "JWT_SECRET is not securely configured. "
                "Set a strong secret in config/.env for non-development mode."
            )
        if unsafe_redis_password:
            raise RuntimeError(
                "REDIS_PASSWORD is not securely configured. "
                "Set a strong secret in config/.env for non-development mode."
            )

    if OPERATING_MODE == 'development':
        if unsafe_password:
            logger.warning(
                f"[WARNING] [{PRINT_PREFIX}] Using default POSTGRESQL_PASSWORD in development. "
                "Do not use this value in production."
            )
        if unsafe_pepper:
            logger.warning(
                f"[WARNING] [{PRINT_PREFIX}] Using default API_KEY_PEPPER in development. "
                "Do not use this value in production."
            )
        if unsafe_password_pepper:
            logger.warning(
                f"[WARNING] [{PRINT_PREFIX}] Using default PASSWORD_PEPPER in development. "
                "Do not use this value in production."
            )
        if unsafe_jwt_secret:
            logger.warning(
                f"[WARNING] [{PRINT_PREFIX}] Using default JWT_SECRET in development. "
                "Do not use this value in production."
            )
        if unsafe_redis_password:
            logger.warning(
                f"[WARNING] [{PRINT_PREFIX}] Using default REDIS_PASSWORD in development. "
                "Do not use this value in production."
            )

_enforce_secret_safety()

logger.info(f"[INFO] [{PRINT_PREFIX}] Loaded environment variables from {_env_path}.")
logger.debug(f"[DEBUG] [{PRINT_PREFIX}] Operating mode: {OPERATING_MODE}, API enabled: {API_ENABLED}, API port: {API_PORT}")
