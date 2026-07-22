from src.api.system.user_db_endpoints.routes.router import router

PRINT_PREFIX = "USER DB ROUTE INIT"

from src.api.system.user_db_endpoints.routes import _get_routes
from src.api.system.user_db_endpoints.routes import _post_routes
from src.api.system.user_db_endpoints.routes import _patch_routes
from src.api.system.user_db_endpoints.routes import _delete_routes
from src.services.system.logging import log_message

log_message(f"[DEBUG] [{PRINT_PREFIX}] User DB route modules imported and registered.")
