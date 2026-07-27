from fastapi import Depends, HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import delete_user
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.delete("/{username}")
@with_ip_block
async def remove_user(request: Request, username: str, api_key: ApiKey = Depends(require_super_admin)):
    deleted = await delete_user(username)
    if not deleted:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {"message": f"User '{username}' deleted successfully."}
