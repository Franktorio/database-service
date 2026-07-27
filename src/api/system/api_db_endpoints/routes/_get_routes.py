# ~/src/api/api_db_endpoints/routes/_get_routes.py

from fastapi import Depends, Request

from src.api.system.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import get_api_keys
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)

@router.get("")
@with_ip_block
async def list_api_keys(request: Request, api_key: ApiKey = Depends(require_super_admin)):
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
