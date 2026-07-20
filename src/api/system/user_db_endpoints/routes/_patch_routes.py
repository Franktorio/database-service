from fastapi import HTTPException

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
from src.services.logging import log_message

PRINT_PREFIX = "PATCH USER DB ROUTES"


@router.patch("/update")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def patch_user(request: UserUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user update request for username {request.username}.")
    updated = await update_user(
        request.username,
        new_email=request.new_email,
        new_role=request.new_role,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{request.username}' not found.")

    return {
        "message": "User updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "email": updated.email,
            "role": updated.role,
            "login_rate_limit": updated.login_rate_limit,
            "hash_algorithm": updated.hash_algorithm,
            "hash_iterations": updated.hash_iterations,
        },
    }


@router.patch("/password")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def patch_user_password(request: UserPasswordUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user password update request for username {request.username}.")

    new_password_hash, new_password_salt = hash_password(
        request.new_password,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    updated = await update_user_password(
        request.username,
        new_password_hash=new_password_hash,
        new_password_salt=new_password_salt,
        new_hash_iterations=PASSWORD_HASH_ITERATIONS,
        new_hash_algorithm=PASSWORD_HASH_ALGORITHM,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{request.username}' not found.")

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
async def patch_user_login_rate_limit(request: UserLoginRateLimitUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received login-rate-limit update request for username {request.username}.")

    updated = await update_user_login_rate_limit(
        request.username,
        new_login_rate_limit=request.new_login_rate_limit,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail=f"User '{request.username}' not found.")

    return {
        "message": "User login rate limit updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "login_rate_limit": updated.login_rate_limit,
            "last_updated_at": updated.last_updated_at,
        },
    }
