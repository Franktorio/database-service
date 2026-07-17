# ~/src/api/api_db_endpoints/routes/_get_routes.py

from fastapi import Request

from src.api.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.api.models import RequestBase
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import get_api_keys
from src.services.logging import log_message

PRINT_PREFIX = "GET API DB ROUTES"


@router.get("/")
@with_ip_block
async def api_db_root(endpoint_request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received GET /api/db/keys request.")
    return {"message": "API key administration endpoint is online."}


@router.post("/list")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def list_api_keys(request: RequestBase, endpoint_request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received API key list request.")
    api_keys = await get_api_keys()
    if not api_keys:
        log_message(f"[INFO] [{PRINT_PREFIX}] No API keys found.")
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
