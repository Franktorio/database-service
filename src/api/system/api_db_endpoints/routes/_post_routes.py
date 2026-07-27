# ~/src/api/api_db_endpoints/routes/_post_routes.py

from src.api.system.api_db_endpoints.routes.router import router
from fastapi import Depends, HTTPException, Request

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.security.tokens import create_api_key
from src.security.validation.api_security import api_key_authorized_factory
from src.security.ip_block import with_ip_block
from src.api.system.api_db_endpoints.models import ApiKeyCreateRequest, ApiKeyPatchRequest
from src.models.crud.system.api_key_crud import update_api_key
from src.models.tables.system.api_key_table import ApiKey

require_super_admin = api_key_authorized_factory(SUPER_ADMIN_LEVEL)


@router.post("")
@with_ip_block
async def create_key(request: Request, model: ApiKeyCreateRequest, api_key: ApiKey = Depends(require_super_admin)):
    if model.permission_level >= SUPER_ADMIN_LEVEL:
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN keys can only be created from the bootstrap script.",
        )

    token = await create_api_key(
        permission_level=model.permission_level,
        rate_limit=model.rate_limit,
        email=model.email,
    )

    return {
        "message": "API key created successfully.",
        "api_key": {
            "token": token,
            "permission_level": model.permission_level,
            "permission_name": PERM_LEVEL_MAP.get(model.permission_level, "UNKNOWN"),
            "rate_limit": model.rate_limit,
            "email": model.email,
        },
    }


@router.patch("/{key_hash}")
@with_ip_block
async def patch_key(request: Request, key_hash: str, model: ApiKeyPatchRequest, api_key: ApiKey = Depends(require_super_admin)):
    if model.new_permission_level is not None and model.new_permission_level >= SUPER_ADMIN_LEVEL:
        raise HTTPException(
            status_code=403,
            detail="SUPER_ADMIN keys can only be created from the bootstrap script.",
        )

    updated_api_key = await update_api_key(
        key_hash,
        new_permission_level=model.new_permission_level,
        new_rate_limit=model.new_rate_limit,
        new_email=model.new_email,
    )

    if updated_api_key is None:
        raise HTTPException(status_code=404, detail=f"API key '{key_hash}' not found.")

    return {
        "message": "API key updated successfully.",
        "api_key": {
            **updated_api_key.to_dict(),
            "permission_name": PERM_LEVEL_MAP.get(updated_api_key.permission_level, "UNKNOWN"),
        },
    }
