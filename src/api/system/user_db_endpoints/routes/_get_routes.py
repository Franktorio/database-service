from fastapi import Depends, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.services.system.monitoring import monitored
from src.api.errors import api_error
from src.api.system.user_db_endpoints.models import UserListResponse, UserResponse
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user.user_crud import get_user_by_username, get_users
from src.models.crud.system.user.user_role_crud import get_roles_for_user, get_roles_for_users
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.tables.system.api_key_table import ApiKey
from src.models.database import session_depends

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.get("", response_model=UserListResponse, response_model_exclude_none=True)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def list_users(request: Request, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
    users = await get_users(session=session)
    if not users:
        return {"message": "No users found."}

    roles_by_user = await get_roles_for_users([user.id for user in users], session=session)

    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": roles_by_user.get(user.id, []),
                "role": (roles_by_user.get(user.id) or [""])[0],
                "login_rate_limit": user.login_rate_limit,
                "hash_algorithm": user.hash_algorithm,
                "hash_iterations": user.hash_iterations,
                "created_at": user.created_at,
                "last_updated_at": user.last_updated_at,
            }
            for user in users
        ]
    }


@router.get("/{username}", response_model=UserResponse)
@monitored(measuring="api", operation_type="read")
@with_ip_block
async def get_user(username: str, request: Request, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
    user = await get_user_by_username(username, session=session)
    if user is None:
        raise api_error(404, f"User '{username}' not found.")

    roles = await get_roles_for_user(user.id, session=session)

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": roles,
            "role": roles[0] if roles else "",
            "login_rate_limit": user.login_rate_limit,
            "hash_algorithm": user.hash_algorithm,
            "hash_iterations": user.hash_iterations,
            "created_at": user.created_at,
            "last_updated_at": user.last_updated_at,
        }
    }
