from fastapi import HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import delete_user
from src.security.validation.api_security import api_authentication
from src.security.ip_block import with_ip_block


@router.delete("/{username}")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def remove_user(request: Request, username: str):
    deleted = await delete_user(username)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {"message": f"User '{username}' deleted successfully."}
