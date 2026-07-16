# ~/config/loader.py
# This file is responsible for loading environment variables from a .env file.

import dotenv
import os

PRINT_PREFIX = "CONFIG LOADER"

# Load environment variables from .env file
_env_file = os.getenv('ENV_FILE', '.env')
_env_path = os.path.join(os.path.dirname(__file__), _env_file)
dotenv.load_dotenv(_env_path)

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

# API server configuration
API_ENABLED: bool = os.getenv('API_ENABLED', 'True').lower() in ('true', '1', 't')
API_PORT: int = int(os.getenv('API_PORT', '8000'))
API_KEY_PEPPER: str = os.getenv('API_KEY_PEPPER', 'dev-only-change-me')

print(f"[INFO] [{PRINT_PREFIX}] Loaded environment variables from {_env_path}.")
print(f"[DEBUG] [{PRINT_PREFIX}] Operating mode: {OPERATING_MODE}, API enabled: {API_ENABLED}, API port: {API_PORT}")
