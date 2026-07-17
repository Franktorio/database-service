# ~/src/api/app.py

import uvicorn
import fastapi
from fastapi import Request
from contextlib import asynccontextmanager

from config.loader import API_ENABLED, API_PORT
from src.api.api_db_endpoints import routes as api_db_routes
from src.security.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.models.database import init_db

from src.api.config import VIEW_LEVEL

from src.api.models import RequestBase
from src.services.logging import log_message

PRINT_PREFIX = "API APP"

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan startup started.")
    await init_db()
    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan startup complete.")

    yield

    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan shutdown complete.")

app = fastapi.FastAPI(
    lifespan=lifespan
)
app.include_router(api_db_routes.router)

def start_api_server():
    """Start the API server using Uvicorn."""
    if not API_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] API server is disabled in the configuration.")
        return
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Registered router tags: {api_db_routes.router.tags}")
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting API server on port {API_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT)
    

@app.get("/")
@with_ip_block
async def root(endpoint_request: Request):
    """Root endpoint for the API service; returns a simple greeting message."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Root endpoint called.")
    return {"message": "Hello from the Nightfall Development Group Database!"}

@app.post("/auth-test")
@with_ip_block
@api_authentication(permission_level=VIEW_LEVEL)
async def auth_test(request: RequestBase, endpoint_request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Auth test endpoint called.")
    return {
        "message": f"API key is valid: {request._api_data}"
    }
