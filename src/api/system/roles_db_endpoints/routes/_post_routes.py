from fastapi import Depends, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.errors import api_error
from src.api.system.roles_db_endpoints.models import RoleCreateRequest, RoleCreateResponse
from src.api.system.roles_db_endpoints.routes.router import router
from src.models.crud.system.user.role_crud import create_role
from src.models.tables.system.api_key_table import ApiKey
from src.security.ip_block import with_ip_block
from src.security.validation.api_security import api_key_authorized_factory
from src.services.system.monitoring import monitored
from src.models.database import session_depends

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.post("", response_model=RoleCreateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def create_role_route(request: Request, model: RoleCreateRequest, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
	try:
		role = await create_role(name=model.name, description=model.description, session=session)
	except ValueError as exc:
		raise api_error(409, str(exc))

	return {
		"message": "Role created successfully.",
		"role": {
			"id": role.id,
			"name": role.name,
			"description": role.description,
			"created_at": role.created_at,
			"last_updated_at": role.last_updated_at,
		},
	}
