# ~/src/api/system/roles_db_endpoints/models.py

from datetime import datetime

from pydantic import BaseModel, Field


class RoleCreateRequest(BaseModel):
    """Request body for creating a role."""

    name: str = Field(..., description="Name of the new role.")
    description: str = Field(default="", description="Optional description of the new role.")
    
    
class RoleUpdateRequest(BaseModel):
    """Request body for updating a role's metadata."""

    new_name: str | None = Field(default=None, description="Optional replacement name for the role.")
    new_description: str | None = Field(default=None, description="Optional replacement description for the role.")


class RoleItem(BaseModel):
    """Full shape of a stored role, as returned by the list/get endpoints."""

    id: int = Field(..., description="Internal numeric identifier for the role row.")
    name: str = Field(..., description="Name of the role.")
    description: str = Field(..., description="Description of the role.")
    created_at: datetime = Field(..., description="When the role was created.")
    last_updated_at: datetime = Field(..., description="When the role was last updated.")
    
    
class RoleCreateResponse(BaseModel):
    """Response body for `POST /api/db/roles`."""

    role: RoleItem = Field(..., description="The newly created role.")
    message: str | None = Field(default=None, description="Optional informational message.")
    

class RoleUpdateResponse(BaseModel):
    """Response body for `PUT /api/db/roles/{role_id}`."""

    role: RoleItem = Field(..., description="The updated role.")
    message: str | None = Field(default=None, description="Optional informational message.")
    

class RoleListResponse(BaseModel):
    """Response body for `GET /api/db/roles`."""

    roles: list[RoleItem] | None = Field(default=None, description="All stored roles, present only when at least one exists.")
    message: str | None = Field(default=None, description="Optional informational message.")


class RoleResponse(BaseModel):
    """Response body for `GET /api/db/roles/{role_id}`."""

    role: RoleItem = Field(..., description="The requested role.")


class MessageResponse(BaseModel):
    """Generic message-only response body, used for `DELETE /api/db/roles/{role_id}`."""

    message: str = Field(..., description="Human-readable result message.")