# ~/src/api/api_db_endpoints/routes/_delete_routes.py

from src.api.system.api_db_endpoints.routes.router import router
from fastapi import HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.security.validation.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import delete_api_key
from src.services.system.logging import log_message

PRINT_PREFIX = "DELETE API DB ROUTES"


@router.delete("/{key_hash}")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def delete_key(request: Request, key_hash: str):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received REST API key delete request for hash {key_hash}.")

    deleted = await delete_api_key(key_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail="API key not found.")

    return {"message": "API key deleted successfully."}
