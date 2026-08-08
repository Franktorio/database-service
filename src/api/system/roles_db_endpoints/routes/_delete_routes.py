from fastapi import Depends, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.errors import api_error
from src.api.system.roles_db_endpoints.models import MessageResponse
from src.api.system.roles_db_endpoints.routes.router import router
from src.models.crud.system.user.role_crud import delete_role_by_id
from src.models.tables.system.api_key_table import ApiKey
from src.security.ip_block import with_ip_block
from src.security.validation.api_security import api_key_authorized_factory
from src.services.system.monitoring import monitored

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.delete("/{role_id}", response_model=MessageResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def remove_role(role_id: int, request: Request, api_key: ApiKey = Depends(require_super_admin)):
    try:
        deleted = await delete_role_by_id(role_id)
    except ValueError as exc:
        raise api_error(409, str(exc))

    if not deleted:
        raise api_error(404, f"Role '{role_id}' not found.")

    return {"message": f"Role '{role_id}' deleted successfully."}
