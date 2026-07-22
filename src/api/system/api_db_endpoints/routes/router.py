# ~/src/api/api_db_endpoints/routes/router.py

from fastapi import APIRouter
from src.services.system.logging import log_message

PRINT_PREFIX = "API DB ROUTER"

router = APIRouter(prefix="/api/db/keys", tags=["api-db-keys"])

log_message(f"[DEBUG] [{PRINT_PREFIX}] API DB router initialized with prefix '/api/db/keys'.")
