from fastapi import HTTPException

from config.loader import PASSWORD_HASH_ALGORITHM, PASSWORD_HASH_ITERATIONS
from src.api.config import SUPER_ADMIN_LEVEL
from src.api.system.user_db_endpoints.models import UserCreateRequest
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user_crud import add_user, get_user_by_username
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.security.tokens import hash_password
from src.services.logging import log_message

PRINT_PREFIX = "POST USER DB ROUTES"


@router.post("/create")
@with_ip_block
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def create_user(request: UserCreateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received user create request for username {request.username}.")

    existing_user = await get_user_by_username(request.username)
    if existing_user is not None:
        raise HTTPException(status_code=409, detail=f"User '{request.username}' already exists.")

    password_hash, password_salt = hash_password(
        request.password,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    created_user = await add_user(
        username=request.username,
        password_hash=password_hash,
        password_salt=password_salt,
        hash_iterations=PASSWORD_HASH_ITERATIONS,
        hash_algorithm=PASSWORD_HASH_ALGORITHM,
        email=request.email,
        initial_role=request.initial_role,
        login_rate_limit=request.login_rate_limit,
    )

    return {
        "message": "User created successfully.",
        "user": {
            "id": created_user.id,
            "username": created_user.username,
            "email": created_user.email,
            "roles": created_user.roles,
            "login_rate_limit": created_user.login_rate_limit,
            "hash_algorithm": created_user.hash_algorithm,
            "hash_iterations": created_user.hash_iterations,
        },
    }
