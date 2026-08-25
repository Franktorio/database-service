from fastapi import Depends, Request

from config.loader import PASSWORD_HASH_ALGORITHM, PASSWORD_HASH_ITERATIONS
from src.api.config import SUPER_ADMIN_LEVEL
from src.services.system.monitoring import monitored
from src.api.errors import api_error
from src.api.system.user_db_endpoints.models import (
    UserLoginRateLimitUpdateRequest,
    UserLoginRateLimitUpdateResponse,
    UserPasswordUpdateRequest,
    UserPasswordUpdateResponse,
    UserUpdateRequest,
    UserUpdateResponse,
)
from src.api.system.user_db_endpoints.routes.router import router
from src.models.crud.system.user.user_crud import (
    get_user_by_username,
    set_user_roles,
    update_user,
    update_user_login_rate_limit,
    update_user_password,
)
from src.models.crud.system.user.user_role_crud import get_roles_for_user
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.security.tokens import hash_password
from src.models.tables.system.api_key_table import ApiKey
from src.models.database import session_depends

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.patch("/{username}", response_model=UserUpdateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def patch_user(username: str, request: Request, model: UserUpdateRequest, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
    user = await get_user_by_username(username, session=session)
    if user is None:
        raise api_error(404, f"User '{username}' not found.")

    if model.new_email is not None:
        updated = await update_user(username, new_email=model.new_email, session=session)
        if updated is None:
            raise api_error(404, f"User '{username}' not found.")
        user = updated

    wants_role_change = model.set_roles is not None or model.add_role is not None or model.remove_role is not None
    if wants_role_change:
        try:
            roles = await set_user_roles(
                username,
                set_roles=model.set_roles,
                add_role=model.add_role,
                remove_role=model.remove_role,
                session=session,
            )
        except ValueError as exc:
            raise api_error(400, str(exc))
        if roles is None:
            raise api_error(404, f"User '{username}' not found.")
    else:
        roles = await get_roles_for_user(user.id, session=session)

    return {
        "message": "User updated successfully.",
        "user": {
            "id": user.id,
            "username": user.username,
            "email": user.email,
            "roles": roles,
            "role": roles[0] if roles else "",
            "login_rate_limit": user.login_rate_limit,
            "hash_algorithm": user.hash_algorithm,
            "hash_iterations": user.hash_iterations,
        },
    }


@router.patch("/{username}/password", response_model=UserPasswordUpdateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def patch_user_password(username: str, request: Request, model: UserPasswordUpdateRequest, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
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
        session=session,
    )
    if updated is None:
        raise api_error(404, f"User '{username}' not found.")

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


@router.patch("/{username}/login-rate-limit", response_model=UserLoginRateLimitUpdateResponse)
@monitored(measuring="api", operation_type="write")
@with_ip_block
async def patch_user_login_rate_limit(username: str, request: Request, model: UserLoginRateLimitUpdateRequest, api_key: ApiKey = Depends(require_super_admin), session=Depends(session_depends)):
    updated = await update_user_login_rate_limit(
        username,
        new_login_rate_limit=model.new_login_rate_limit,
        session=session,
    )
    if updated is None:
        raise api_error(404, f"User '{username}' not found.")

    return {
        "message": "User login rate limit updated successfully.",
        "user": {
            "id": updated.id,
            "username": updated.username,
            "login_rate_limit": updated.login_rate_limit,
            "last_updated_at": updated.last_updated_at,
        },
    }
