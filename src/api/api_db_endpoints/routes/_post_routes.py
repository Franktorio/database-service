# ~/src/api/api_db_endpoints/routes/_post_routes.py

from src.api.api_db_endpoints.routes.router import router

from src.api.config import SUPER_ADMIN_LEVEL, PERM_LEVEL_MAP
from src.api.keys import create_api_key, hash_token
from src.api.validate import with_validation
from src.api.api_db_endpoints.models import ApiKeyCreateRequest, ApiKeyUpdateRequest
from src.models.crud.api_key_crud import update_api_key

PRINT_PREFIX = "POST API DB ROUTES"


@router.post("/create")
@with_validation(permission_level=SUPER_ADMIN_LEVEL)
async def create_key(request: ApiKeyCreateRequest):
    print(f"[DEBUG] [{PRINT_PREFIX}] Received API key create request.")

    if request.permission_level >= SUPER_ADMIN_LEVEL:
        print(f"[WARNING] [{PRINT_PREFIX}] Super-admin key creation rejected from API.")
        return {"error": "SUPER_ADMIN keys can only be created from the bootstrap script."}, 403

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
@with_validation(permission_level=SUPER_ADMIN_LEVEL)
async def update_key(request: ApiKeyUpdateRequest):
    print(f"[DEBUG] [{PRINT_PREFIX}] Received API key update request for hash {request.key_hash}.")

    if request.new_permission_level is not None and request.new_permission_level >= SUPER_ADMIN_LEVEL:
        print(f"[WARNING] [{PRINT_PREFIX}] Super-admin key updates are restricted to the bootstrap script.")
        return {"error": "SUPER_ADMIN keys can only be created from the bootstrap script."}, 403

    updated_api_key = await update_api_key(
        request.key_hash,
        new_permission_level=request.new_permission_level,
        new_rate_limit=request.new_rate_limit,
        new_email=request.new_email,
    )
    if updated_api_key is None:
        return {"error": f"API key '{request.key_hash}' not found."}, 404

    return {
        "message": "API key updated successfully.",
        "api_key": {
            **updated_api_key.to_dict(),
            "permission_name": PERM_LEVEL_MAP.get(updated_api_key.permission_level, "UNKNOWN"),
        },
    }