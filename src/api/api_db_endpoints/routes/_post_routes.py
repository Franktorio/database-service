# ~/src/api/api_db_endpoints/routes/_post_routes.py

from src.api.api_db_endpoints.routes.router import router
from fastapi import HTTPException

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.security.tokens import create_api_key, hash_token
from src.security.api_security import api_authentication
from src.api.api_db_endpoints.models import ApiKeyCreateRequest, ApiKeyUpdateRequest
from src.models.crud.system.api_key_crud import update_api_key
from src.services.logging import log_message

PRINT_PREFIX = "POST API DB ROUTES"


@router.post("/create")
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def create_key(request: ApiKeyCreateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received API key create request.")

    if request.permission_level >= SUPER_ADMIN_LEVEL:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Super-admin key creation rejected from API.")
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN keys can only be created from the bootstrap script.",
        )

    token = await create_api_key(
        permission_level=request.permission_level,
        rate_limit=request.rate_limit,
        email=request.email,
    )
    key_hash = hash_token(token)

    return {
        "message": "API key created successfully.",
        "api_key": {
            "token": token,
            "key_hash": key_hash,
            "permission_level": request.permission_level,
            "permission_name": PERM_LEVEL_MAP.get(request.permission_level, "UNKNOWN"),
            "rate_limit": request.rate_limit,
            "email": request.email,
        },
    }


@router.post("/update")
@api_authentication(permission_level=SUPER_ADMIN_LEVEL)
async def update_key(request: ApiKeyUpdateRequest):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Received API key update request for hash {request.key_hash}.")

    if request.new_permission_level is not None and request.new_permission_level >= SUPER_ADMIN_LEVEL:
        log_message(f"[WARNING] [{PRINT_PREFIX}] Super-admin key updates are restricted to the bootstrap script.")
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN keys can only be created from the bootstrap script.",
        )

    updated_api_key = await update_api_key(
        request.key_hash,
        new_permission_level=request.new_permission_level,
        new_rate_limit=request.new_rate_limit,
        new_email=request.new_email,
    )
    if updated_api_key is None:
        raise HTTPException(status_code=404, detail=f"API key '{request.key_hash}' not found.")

    return {
        "message": "API key updated successfully.",
        "api_key": {
            **updated_api_key.to_dict(),
            "permission_name": PERM_LEVEL_MAP.get(updated_api_key.permission_level, "UNKNOWN"),
        },
    }
