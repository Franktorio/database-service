# ~/src/api/api_db_endpoints/models.py
# Request models for API-key administration endpoints.

from typing import Optional
from pydantic import BaseModel, Field

from src.api.config import VIEW_LEVEL, SUPER_ADMIN_LEVEL


class ApiKeyCreateRequest(BaseModel):
    """Request body for creating a new API key."""

    permission_level: int = Field(default=VIEW_LEVEL, ge=VIEW_LEVEL, le=SUPER_ADMIN_LEVEL, description="Permission level for the new API key.")
    rate_limit: int = Field(default=1000, ge=1, description="Maximum number of requests per minute.")
    email: Optional[str] = Field(default=None, description="Optional email address associated with the API key.")

class ApiKeyPatchRequest(BaseModel):
    """Request body for RESTful API key patch endpoint."""

    new_permission_level: Optional[int] = Field(default=None, ge=VIEW_LEVEL, le=SUPER_ADMIN_LEVEL, description="Optional replacement permission level.")
    new_rate_limit: Optional[int] = Field(default=None, ge=1, description="Optional replacement requests-per-minute limit.")
    new_email: Optional[str] = Field(default=None, description="Optional replacement email associated with the API key.")
