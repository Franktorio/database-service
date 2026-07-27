# Request/response models for user database administration endpoints.

from datetime import datetime

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

    new_email: str | None = Field(default=None, description="Optional replacement email.")
    set_roles: list[str] | None = Field(default=None, description="Optional full replacement role list.")
    add_role: str | None = Field(default=None, description="Optional role to add.")
    remove_role: str | None = Field(default=None, description="Optional role to remove.")


class UserPasswordUpdateRequest(BaseModel):
    """Request body for updating a user's password."""

    new_password: str = Field(..., description="New password value.")


class UserLoginRateLimitUpdateRequest(BaseModel):
    """Request body for updating a user's login rate limit."""

    new_login_rate_limit: int = Field(..., ge=1, description="New login rate limit per minute.")


class UserItem(BaseModel):
    """Full shape of a stored user, as returned by the list/get endpoints."""

    id: int = Field(..., description="Internal numeric identifier for the user row.")
    username: str = Field(..., description="Username of the user.")
    email: str = Field(..., description="Email address of the user.")
    roles: list[str] = Field(..., description="All roles assigned to the user.")
    role: str = Field(..., description="Primary (first) role of the user.")
    login_rate_limit: int = Field(..., description="Allowed login attempts per LOGIN_TIME_WINDOW.")
    hash_algorithm: str = Field(..., description="Password hashing algorithm used for this user.")
    hash_iterations: int = Field(..., description="Number of hashing iterations used for this user's password.")
    created_at: datetime = Field(..., description="When the user was created.")
    last_updated_at: datetime = Field(..., description="When the user was last updated.")


class UserListResponse(BaseModel):
    """Response body for `GET /api/db/users`."""

    users: list[UserItem] | None = Field(default=None, description="All stored users, present only when at least one exists.")
    message: str | None = Field(default=None, description="Informational message, present only when no users exist.")


class UserResponse(BaseModel):
    """Response body for `GET /api/db/users/{username}`."""

    user: UserItem = Field(..., description="The requested user.")


class UserCreated(BaseModel):
    """Shape of a newly created user (no timestamps/primary role yet)."""

    id: int = Field(..., description="Internal numeric identifier for the user row.")
    username: str = Field(..., description="Username of the new user.")
    email: str = Field(..., description="Email address of the new user.")
    roles: list[str] = Field(..., description="All roles assigned to the new user.")
    login_rate_limit: int = Field(..., description="Allowed login attempts per LOGIN_TIME_WINDOW.")
    hash_algorithm: str = Field(..., description="Password hashing algorithm used for this user.")
    hash_iterations: int = Field(..., description="Number of hashing iterations used for this user's password.")


class UserCreateResponse(BaseModel):
    """Response body for `POST /api/db/users`."""

    message: str = Field(..., description="Human-readable result message.")
    user: UserCreated = Field(..., description="The newly created user.")


class UserUpdated(BaseModel):
    """Shape of a user after a metadata update (no timestamps)."""

    id: int = Field(..., description="Internal numeric identifier for the user row.")
    username: str = Field(..., description="Username of the user.")
    email: str = Field(..., description="Email address of the user.")
    roles: list[str] = Field(..., description="All roles assigned to the user.")
    role: str = Field(..., description="Primary (first) role of the user.")
    login_rate_limit: int = Field(..., description="Allowed login attempts per LOGIN_TIME_WINDOW.")
    hash_algorithm: str = Field(..., description="Password hashing algorithm used for this user.")
    hash_iterations: int = Field(..., description="Number of hashing iterations used for this user's password.")


class UserUpdateResponse(BaseModel):
    """Response body for `PATCH /api/db/users/{username}`."""

    message: str = Field(..., description="Human-readable result message.")
    user: UserUpdated = Field(..., description="The updated user.")


class UserPasswordUpdated(BaseModel):
    """Shape of a user after a password rotation."""

    id: int = Field(..., description="Internal numeric identifier for the user row.")
    username: str = Field(..., description="Username of the user.")
    hash_algorithm: str = Field(..., description="Password hashing algorithm used for this user.")
    hash_iterations: int = Field(..., description="Number of hashing iterations used for this user's password.")
    last_updated_at: datetime = Field(..., description="When the user was last updated.")


class UserPasswordUpdateResponse(BaseModel):
    """Response body for `PATCH /api/db/users/{username}/password`."""

    message: str = Field(..., description="Human-readable result message.")
    user: UserPasswordUpdated = Field(..., description="The user whose password was rotated.")


class UserLoginRateLimitUpdated(BaseModel):
    """Shape of a user after a login rate limit update."""

    id: int = Field(..., description="Internal numeric identifier for the user row.")
    username: str = Field(..., description="Username of the user.")
    login_rate_limit: int = Field(..., description="Updated allowed login attempts per LOGIN_TIME_WINDOW.")
    last_updated_at: datetime = Field(..., description="When the user was last updated.")


class UserLoginRateLimitUpdateResponse(BaseModel):
    """Response body for `PATCH /api/db/users/{username}/login-rate-limit`."""

    message: str = Field(..., description="Human-readable result message.")
    user: UserLoginRateLimitUpdated = Field(..., description="The user whose login rate limit was updated.")


class MessageResponse(BaseModel):
    """Generic message-only response body, used for `DELETE /api/db/users/{username}`."""

    message: str = Field(..., description="Human-readable result message.")

