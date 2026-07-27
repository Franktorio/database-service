from fastapi import Depends, HTTPException, Request

from config.loader import PASSWORD_HASH_ALGORITHM, PASSWORD_HASH_ITERATIONS
from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.models import (
    UserLoginRateLimitUpdateRequest,
    UserPasswordUpdateRequest,
    UserUpdateRequest,
)
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import (
    update_user,
    update_user_login_rate_limit,
    update_user_password,
)
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.security.tokens import hash_password
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.patch("/{username}")
@with_ip_block
async def patch_user(username: str, request: Request, model: UserUpdateRequest, api_key: ApiKey = Depends(require_super_admin)):
    try:
        updated = await update_user(
            username,
            new_email=model.new_email,
            set_roles=model.set_roles,
            add_role=model.add_role,
            remove_role=model.remove_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {
        "message": "User updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "email": updated.email,
            "roles": updated.roles,
            "role": updated.role,
            "login_rate_limit": updated.login_rate_limit,
            "hash_algorithm": updated.hash_algorithm,
            "hash_iterations": updated.hash_iterations,
        },
    }


@router.patch("/{username}/password")
@with_ip_block
async def patch_user_password(username: str, request: Request, model: UserPasswordUpdateRequest, api_key: ApiKey = Depends(require_super_admin)):
    new_password_hash, new_password_salt = hash_password(
        model.new_password,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    updated = await update_user_password(
        username,
        new_password_hash=new_password_hash,
        new_password_salt=new_password_salt,
        new_hash_iterations=PASSWORD_HASH_ITERATIONS,
        new_hash_algorithm=PASSWORD_HASH_ALGORITHM,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {
        "message": "User password updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "hash_algorithm": updated.hash_algorithm,
            "hash_iterations": updated.hash_iterations,
            "last_updated_at": updated.last_updated_at,
        },
    }


@router.patch("/{username}/login-rate-limit")
@with_ip_block
async def patch_user_login_rate_limit(username: str, request: Request, model: UserLoginRateLimitUpdateRequest, api_key: ApiKey = Depends(require_super_admin)):
    updated = await update_user_login_rate_limit(
        username,
        new_login_rate_limit=model.new_login_rate_limit,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{username}' not found.")

    return {
        "message": "User login rate limit updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "login_rate_limit": updated.login_rate_limit,
            "last_updated_at": updated.last_updated_at,
        },
    }
