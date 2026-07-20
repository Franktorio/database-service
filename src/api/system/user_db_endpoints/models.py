# Request models for user database administration endpoints.

from src.api.models import APIRequestBase


class UserCreateRequest(APIRequestBase):
    """Request body for creating a user account."""

    username: str
    password: str
    initial_role: str
    email: str = ""
    login_rate_limit: int = 10


class UserUpdateRequest(APIRequestBase):
    """Request body for updating a user's metadata."""

    username: str
    new_email: str | None = None
    set_roles: list[str] | None = None
    add_role: str | None = None
    remove_role: str | None = None


class UserPasswordUpdateRequest(APIRequestBase):
    """Request body for updating a user's password."""

    username: str
    new_password: str


class UserLoginRateLimitUpdateRequest(APIRequestBase):
    """Request body for updating a user's login rate limit."""

    username: str
    new_login_rate_limit: int


class UserDeleteRequest(APIRequestBase):
    """Request body for deleting a user."""

    username: str
