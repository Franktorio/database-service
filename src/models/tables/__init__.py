from .system import api_key_table
from .system import user_table
from .system import auth_cookie_table
from .system import persistent_logs
from src.services.logging import log_message

PRINT_PREFIX = "TABLES INIT"

# These import are just to register the tables with the Base

log_message(f"[DEBUG] [{PRINT_PREFIX}] SQLAlchemy table modules imported and registered.")
