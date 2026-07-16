# ~/src/api/api_db_endpoints/routes/_delete_routes.py

from src.api.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.api_db_endpoints.models import ApiKeyDeleteRequest
from src.api.validate import with_validation
from src.models.crud.api_key_crud import delete_api_key

PRINT_PREFIX = "DELETE API DB ROUTES"


@router.delete("/delete")
@with_validation(permission_level=SUPER_ADMIN_LEVEL)
async def delete_key(request: ApiKeyDeleteRequest):
    print(f"[DEBUG] [{PRINT_PREFIX}] Received API key delete request for hash {request.key_hash}.")

    deleted = await delete_api_key(request.key_hash)
    if not deleted:
        return {"error": f"API key '{request.key_hash}' not found."}, 404

    return {"message": f"API key '{request.key_hash}' deleted successfully."}