# ~/src/api/models.py
# Shared API request models.

from pydantic import BaseModel, Field
from src.services.logging import log_message

PRINT_PREFIX = "API MODELS"

class APIRequestBase(BaseModel):
    """Base class for all API request models."""

    api_key: str = Field(..., description="API key used to authorize the request.")

class JWTRequestBase(BaseModel):
    """Base class for all JWT request models."""

    auth_token: str = Field(..., description="JWT auth token provided by the client.")
    
class LoginRequestBase(BaseModel):
    """Base class for login request models."""

    username: str = Field(..., description="Username for login.")
    password: str = Field(..., description="Password for login.")

log_message(f"[DEBUG] [{PRINT_PREFIX}] Base request model loaded.")


