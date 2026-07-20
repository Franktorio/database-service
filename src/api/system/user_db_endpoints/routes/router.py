from fastapi import APIRouter
from src.services.logging import log_message

PRINT_PREFIX = "USER DB ROUTER"

router = APIRouter(prefix="/api/db/users", tags=["api-db-users"])

log_message(f"[DEBUG] [{PRINT_PREFIX}] User DB router initialized with prefix '/api/db/users'.")
