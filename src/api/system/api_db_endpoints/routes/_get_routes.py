# ~/src/api/api_db_endpoints/routes/_get_routes.py

from fastapi import Request

from src.api.system.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.security.validation.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import get_api_keys

@router.get("")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def list_api_keys(request: Request):
    api_keys = await get_api_keys()
    if not api_keys:
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
