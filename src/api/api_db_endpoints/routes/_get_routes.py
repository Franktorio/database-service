# ~/src/api/api_db_endpoints/routes/_get_routes.py

from src.api.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.api.models import RequestBase
from src.api.validate import with_validation
from src.models.crud.api_key_crud import get_api_keys

PRINT_PREFIX = "GET API DB ROUTES"


@router.get("/")
async def api_db_root():
    print(f"[DEBUG] [{PRINT_PREFIX}] Received GET /api/db/keys request.")
    return {"message": "API key administration endpoint is online."}


@router.post("/list")
@with_validation(permission_level=SUPER_ADMIN_LEVEL)
async def list_api_keys(request: RequestBase):
    print(f"[DEBUG] [{PRINT_PREFIX}] Received API key list request.")
    api_keys = await get_api_keys()
    if not api_keys:
        print(f"[INFO] [{PRINT_PREFIX}] No API keys found.")
        return {"message": "No API keys found."}

    return {
        "api_keys": [
            {
                **api_key.to_dict(),
                "permission_name": PERM_LEVEL_MAP.get(api_key.permission_level, "UNKNOWN"),
            }
            for api_key in api_keys
        ]
    }