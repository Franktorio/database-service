# ~/src/api/api_db_endpoints/models.py
# Request models for API-key administration endpoints.

from typing import Optional

from src.api.config import VIEW_LEVEL
from src.api.models import APIRequestBase
from src.services.logging import log_message

PRINT_PREFIX = "API DB MODELS"


class ApiKeyCreateRequest(APIRequestBase):
    """Request body for creating a new API key."""

    permission_level: int = VIEW_LEVEL
    rate_limit: int = 1000
    email: str = ""


class ApiKeyUpdateRequest(APIRequestBase):
    """Request body for updating an existing API key."""

    key_hash: str
    new_permission_level: Optional[int] = None
    new_rate_limit: Optional[int] = None
    new_email: Optional[str] = None


class ApiKeyDeleteRequest(APIRequestBase):
    """Request body for deleting an API key token."""

    target_api_key: str


log_message(f"[DEBUG] [{PRINT_PREFIX}] API key admin request models loaded.")
