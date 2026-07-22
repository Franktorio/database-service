from fastapi import HTTPException, Request

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
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.security.tokens import hash_password
from src.services.system.logging import log_message

PRINT_PREFIX = "PATCH USER DB ROUTES"


@router.patch("/update")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def patch_user(request: Request, model: UserUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user update request for username {model.username}.")
    try:
        updated = await update_user(
            model.username,
            new_email=model.new_email,
            set_roles=model.set_roles,
            add_role=model.add_role,
            remove_role=model.remove_role,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{model.username}' not found.")

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


@router.patch("/password")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def patch_user_password(request: Request, model: UserPasswordUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user password update request for username {model.username}.")

    new_password_hash, new_password_salt = hash_password(
        model.new_password,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    updated = await update_user_password(
        model.username,
        new_password_hash=new_password_hash,
        new_password_salt=new_password_salt,
        new_hash_iterations=PASSWORD_HASH_ITERATIONS,
        new_hash_algorithm=PASSWORD_HASH_ALGORITHM,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{model.username}' not found.")

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


@router.patch("/login-rate-limit")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def patch_user_login_rate_limit(request: Request, model: UserLoginRateLimitUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received login-rate-limit update request for username {model.username}.")

    updated = await update_user_login_rate_limit(
        model.username,
        new_login_rate_limit=model.new_login_rate_limit,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{model.username}' not found.")

    return {
        "message": "User login rate limit updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "login_rate_limit": updated.login_rate_limit,
            "last_updated_at": updated.last_updated_at,
        },
    }
