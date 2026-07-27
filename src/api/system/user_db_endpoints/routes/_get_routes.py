from fastapi import Depends, HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import get_user_by_username, get_users
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.get("")
@with_ip_block
async def list_users(request: Request, api_key: ApiKey = Depends(require_super_admin)):
    users = await get_users()
    if not users:
        return {"message": "No users found."}

    return {
        "users": [
            {
                "id": user.id,
                "username": user.username,
                "email": user.email,
                "roles": user.roles,
                "role": user.role,
                "login_rate_limit": user.login_rate_limit,
                "hash_algorithm": user.hash_algorithm,
                "hash_iterations": user.hash_iterations,
                "created_at": user.created_at,
                "last_updated_at": user.last_updated_at,
            }
            for user in users
        ]
    }


@router.get("/{username}")
@with_ip_block
async def get_user(username: str, request: Request, api_key: ApiKey = Depends(require_super_admin)):
    user = await get_user_by_username(username)
    if user is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": user.roles,
            "role": user.role,
            "login_rate_limit": user.login_rate_limit,
            "hash_algorithm": user.hash_algorithm,
            "hash_iterations": user.hash_iterations,
            "created_at": user.created_at,
            "last_updated_at": user.last_updated_at,
        }
    }
