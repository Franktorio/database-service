from fastapi import HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.models import UserDeleteRequest
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import delete_user
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.services.system.logging import log_message

PRINT_PREFIX = "DELETE USER DB ROUTES"


@router.delete("/delete")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def remove_user(request: Request, model: UserDeleteRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user delete request for username {model.username}.")

    deleted = await delete_user(model.username)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User '{model.username}' not found.")

    return {"message": f"User '{model.username}' deleted successfully."}
