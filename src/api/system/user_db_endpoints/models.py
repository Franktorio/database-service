# Request models for user database administration endpoints.

from pydantic import BaseModel, Field


class UserCreateRequest(BaseModel):
    """Request body for creating a user account."""

    username: str = Field(..., description="Username for the new user.")
    password: str = Field(..., description="Initial password for the new user.")
    initial_role: str = Field(..., description="Initial role assigned to the new user.")
    email: str = Field(default="", description="Email for the user account.")
    login_rate_limit: int = Field(default=10, ge=1, description="Allowed login attempts per minute.")


class UserUpdateRequest(BaseModel):
    """Request body for updating a user's metadata."""

    username: str = Field(..., description="Username of the user to update.")
    new_email: str | None = Field(default=None, description="Optional replacement email.")
    set_roles: list[str] | None = Field(default=None, description="Optional full replacement role list.")
    add_role: str | None = Field(default=None, description="Optional role to add.")
    remove_role: str | None = Field(default=None, description="Optional role to remove.")


class UserPasswordUpdateRequest(BaseModel):
    """Request body for updating a user's password."""

    username: str = Field(..., description="Username of the user whose password is being changed.")
    new_password: str = Field(..., description="New password value.")


class UserLoginRateLimitUpdateRequest(BaseModel):
    """Request body for updating a user's login rate limit."""

    username: str = Field(..., description="Username of the user to update.")
    new_login_rate_limit: int = Field(..., ge=1, description="New login rate limit per minute.")


class UserDeleteRequest(BaseModel):
    """Request body for deleting a user."""

    username: str = Field(..., description="Username of the user to delete.")
