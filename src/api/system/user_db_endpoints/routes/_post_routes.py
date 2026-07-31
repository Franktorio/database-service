from fastapi import Depends, Request

from config.loader import PASSWORD_HASH_ALGORITHM, PASSWORD_HASH_ITERATIONS
from src.services.system.monitoring import monitored
from src.api.config import SUPER_ADMIN_LEVEL
from src.api.errors import api_error
from src.api.system.user_db_endpoints.models import UserCreateRequest, UserCreateResponse
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user.user_crud import create_user, get_user_by_username
from src.models.crud.system.user.user_role_crud import get_roles_for_user
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.security.tokens import hash_password
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.post("", response_model=UserCreateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def create_user_route(request: Request, model: UserCreateRequest, api_key: ApiKey = Depends(require_super_admin)):
    existing_user = await get_user_by_username(model.username)
    if existing_user is not None:
        raise api_error(409, f"User '{model.username}' already exists.")

    password_hash, password_salt = hash_password(
        model.password,
        iterations=PASSWORD_HASH_ITERATIONS,
    )
    created_user = await create_user(
        username=model.username,
        password_hash=password_hash,
        password_salt=password_salt,
        hash_iterations=PASSWORD_HASH_ITERATIONS,
        hash_algorithm=PASSWORD_HASH_ALGORITHM,
        email=model.email,
        initial_role=model.initial_role,
        login_rate_limit=model.login_rate_limit,
    )
    roles = await get_roles_for_user(created_user.id)

    return {
        "message": "User created successfully.",
        "user": {
            "id": created_user.id,
            "username": created_user.username,
            "email": created_user.email,
            "roles": roles,
            "login_rate_limit": created_user.login_rate_limit,
            "hash_algorithm": created_user.hash_algorithm,
            "hash_iterations": created_user.hash_iterations,
        },
    }
