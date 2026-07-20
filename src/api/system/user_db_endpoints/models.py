# Request models for user database administration endpoints.

from src.api.models import APIRequestBase


class UserCreateRequest(APIRequestBase):
    """Request body for creating a user account."""

    username: str
    password: str
    email: str = ""
    role: str = "user"
    login_rate_limit: int = 10


class UserUpdateRequest(APIRequestBase):
    """Request body for updating a user's metadata."""

    username: str
    new_email: str | None = None
    new_role: str | None = None


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
