# ~/src/api/api_db_endpoints/routes/_delete_routes.py

from src.api.api_db_endpoints.routes.router import router
from fastapi import HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.api_db_endpoints.models import ApiKeyDeleteRequest
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.models.crud.system.api_key_crud import delete_api_key
from src.services.logging import log_message

PRINT_PREFIX = "DELETE API DB ROUTES"


@router.delete("/delete")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def delete_key(request: ApiKeyDeleteRequest, endpoint_request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received API key delete request for hash {request.key_hash}.")

    deleted = await delete_api_key(request.key_hash)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"API key '{request.key_hash}' not found.")

    return {"message": f"API key '{request.key_hash}' deleted successfully."}
