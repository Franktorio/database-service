# ~/src/api/api_db_endpoints/routes/_delete_routes.py

from src.api.system.api_db_endpoints.routes.router import router
from fastapi import Depends, HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import delete_api_key
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.delete("/{key_hash}")
@with_ip_block
async def delete_key(request: Request, key_hash: str, api_key: ApiKey = Depends(require_super_admin)):
    deleted = await delete_api_key(key_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found.")

    return {"message": "API key deleted successfully."}
