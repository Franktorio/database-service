# ~/src/api/models.py
# Shared API request models.

from pydantic import BaseModel
from src.services.logging import log_message

PRINT_PREFIX = "API MODELS"

class RequestBase(BaseModel):
    """Base class for all request models."""

    api_key: str


log_message(f"[DEBUG] [{PRINT_PREFIX}] Base request model loaded.")


