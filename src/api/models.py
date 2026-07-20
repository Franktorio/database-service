# ~/src/api/models.py
# Shared API request models.

from pydantic import BaseModel
from src.services.logging import log_message

PRINT_PREFIX = "API MODELS"

class APIRequestBase(BaseModel):
    """Base class for all API request models."""

    api_key: str

class JWTRequestBase(BaseModel):
    """Base class for all JWT request models."""

    auth_token: str
    
class LoginRequestBase(BaseModel):
    """Base class for login request models."""

    username: str
    password: str

log_message(f"[DEBUG] [{PRINT_PREFIX}] Base request model loaded.")


