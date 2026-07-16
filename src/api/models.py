# ~/src/api/models.py
# Shared API request models.

from pydantic import BaseModel

PRINT_PREFIX = "API MODELS"

class RequestBase(BaseModel):
    """Base class for all request models."""

    api_key: str


print(f"[DEBUG] [{PRINT_PREFIX}] Base request model loaded.")

