# ~/src/api/models.py
# Shared API request models.

from pydantic import BaseModel, Field

class JWTRequestBase(BaseModel):
    """Base class for all JWT request models."""

    auth_token: str = Field(..., description="JWT auth token provided by the client.")
    
class LoginRequestBase(BaseModel):
    """Base class for login request models."""

    username: str = Field(..., description="Username for login.")
    password: str = Field(..., description="Password for login.")
    
class APIRequestData(BaseModel):
    """Data model for API request data which is injected into the request context."""
    
    api_key_fingerprint: str = Field(..., description="API key fingerprint provided by the client.")
    permission_level: int = Field(..., description="Permission level of the API key.")
    permission_name: str = Field(..., description="Display name for the permission level.")
    rate_limit: int = Field(..., description="Rate limit for the API key.")

class CookieRequestData(BaseModel):
    """Data model for cookie request data which is injected into the request context."""
    
    username: str = Field(..., description="Username extracted from the cookie.")
    user_id: int | None = Field(default=None, description="User id extracted from the cookie's tracked row.")
    role: str = Field(..., description="Role extracted from the cookie.")
    token_hash: str = Field(..., description="Token hash extracted from the cookie.")
    rate_limit: int = Field(..., description="Rate limit extracted from the cookie.")


