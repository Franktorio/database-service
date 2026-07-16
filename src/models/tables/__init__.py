from . import api_key_table
from src.services.logging import log_message

PRINT_PREFIX = "TABLES INIT"

# These import are just to register the tables with the Base

log_message(f"[DEBUG] [{PRINT_PREFIX}] SQLAlchemy table modules imported and registered.")
