from src.api.api_db_endpoints.routes.router import router

PRINT_PREFIX = "API DB ROUTE INIT"

from src.api.api_db_endpoints.routes import _get_routes
from src.api.api_db_endpoints.routes import _post_routes
from src.api.api_db_endpoints.routes import _delete_routes

print(f"[DEBUG] [{PRINT_PREFIX}] API DB route modules imported and registered.")