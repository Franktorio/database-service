from fastapi import Depends, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.errors import api_error
from src.api.system.roles_db_endpoints.models import RoleUpdateRequest, RoleUpdateResponse
from src.api.system.roles_db_endpoints.routes.router import router
from src.models.crud.system.user.role_crud import get_role_by_id, update_role
from src.models.tables.system.api_key_table import ApiKey
from src.security.ip_block import with_ip_block
from src.security.validation.api_security import api_key_authorized_factory
from src.services.system.monitoring import monitored

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.put("/{role_id}", response_model=RoleUpdateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def put_role(role_id: int, request: Request, model: RoleUpdateRequest, api_key: ApiKey = Depends(require_super_admin)):
    if model.new_name is None and model.new_description is None:
        raise api_error(400, "At least one of 'new_name' or 'new_description' must be provided.")

    existing_role = await get_role_by_id(role_id)
    if existing_role is None:
        raise api_error(404, f"Role '{role_id}' not found.")

    try:
        role = await update_role(role_id=role_id, new_name=model.new_name, new_description=model.new_description)
    except ValueError as exc:
        raise api_error(409, str(exc))

    return {
        "message": "Role updated successfully.",
        "role": {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "created_at": role.created_at,
            "last_updated_at": role.last_updated_at,
        },
    }
