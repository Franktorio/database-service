from fastapi import Depends, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.errors import api_error
from src.api.system.roles_db_endpoints.models import RoleListResponse, RoleResponse
from src.api.system.roles_db_endpoints.routes.router import router
from src.models.crud.system.user.role_crud import get_role_by_id, get_roles
from src.models.tables.system.api_key_table import ApiKey
from src.security.ip_block import with_ip_block
from src.security.validation.api_security import api_key_authorized_factory
from src.services.system.monitoring import monitored

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.get("", response_model=RoleListResponse, response_model_exclude_none=True)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def list_roles(request: Request, api_key: ApiKey = Depends(require_super_admin)):
    roles = await get_roles()
    if not roles:
        return {"message": "No roles found."}

    return {
        "roles": [
            {
                "id": role.id,
                "name": role.name,
                "description": role.description,
                "created_at": role.created_at,
                "last_updated_at": role.last_updated_at,
            }
            for role in roles
        ]
    }


@router.get("/{role_id}", response_model=RoleResponse)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def get_role(role_id: int, request: Request, api_key: ApiKey = Depends(require_super_admin)):
    role = await get_role_by_id(role_id)
    if role is None:
        raise api_error(404, f"Role '{role_id}' not found.")

    return {
        "role": {
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "created_at": role.created_at,
            "last_updated_at": role.last_updated_at,
        }
    }
