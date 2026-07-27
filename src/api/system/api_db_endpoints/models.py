# ~/src/api/api_db_endpoints/models.py
# Request/response models for API-key administration endpoints.

from datetime import datetime
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


class ApiKeyItem(BaseModel):
    """Shape of a single stored API key as returned by the list/patch endpoints."""

    id: int = Field(..., description="Opaque numeric identifier for the API key; used as the path param for PATCH/DELETE.")
    permission_level: int = Field(..., description="Permission level of the API key.")
    permission_name: str = Field(..., description="Display name for the permission level.")
    rate_limit: int = Field(..., description="Requests allowed per RATE_LIMIT_WINDOW_SECONDS.")
    email: Optional[str] = Field(default=None, description="Email address associated with the API key, if any.")
    created_at: datetime = Field(..., description="When the API key was created.")
    last_updated_at: datetime = Field(..., description="When the API key was last updated.")


class ApiKeyListResponse(BaseModel):
    """Response body for `GET /api/db/keys`."""

    api_keys: Optional[list[ApiKeyItem]] = Field(default=None, description="All stored API keys, present only when at least one exists.")
    message: Optional[str] = Field(default=None, description="Informational message, present only when no API keys exist.")


class ApiKeyCreated(BaseModel):
    """Shape of the newly created API key, including its one-time raw token."""

    id: int = Field(..., description="Opaque numeric identifier for the API key; used as the path param for PATCH/DELETE.")
    token: str = Field(..., description="Raw API key token; shown exactly once and never recoverable afterward.")
    permission_level: int = Field(..., description="Permission level of the new API key.")
    permission_name: str = Field(..., description="Display name for the permission level.")
    rate_limit: int = Field(..., description="Requests allowed per RATE_LIMIT_WINDOW_SECONDS.")
    email: Optional[str] = Field(default=None, description="Email address associated with the API key, if any.")


class ApiKeyCreateResponse(BaseModel):
    """Response body for `POST /api/db/keys`."""

    message: str = Field(..., description="Human-readable result message.")
    api_key: ApiKeyCreated = Field(..., description="The newly created API key.")


class ApiKeyPatchResponse(BaseModel):
    """Response body for `PATCH /api/db/keys/{key_id}`."""

    message: str = Field(..., description="Human-readable result message.")
    api_key: ApiKeyItem = Field(..., description="The updated API key.")


class MessageResponse(BaseModel):
    """Generic message-only response body, used for `DELETE /api/db/keys/{key_id}`."""

    message: str = Field(..., description="Human-readable result message.")

