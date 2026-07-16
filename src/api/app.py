# ~/src/api/app.py

import uvicorn
import fastapi
from contextlib import asynccontextmanager

from config.loader import API_ENABLED, API_PORT
from src.api.api_db_endpoints import routes as api_db_routes
from src.api.validate import with_validation
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
async def root():
    """Root endpoint for the API service; returns a simple greeting message."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Root endpoint called.")
    return {"message": "Hello from the Nightfall Development Group Database!"}

@app.post("/auth-test")
@with_validation(permission_level=VIEW_LEVEL)
async def auth_test(request: RequestBase):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Auth test endpoint called.")
    return {
        "message": f"API key is valid: {request._api_data}"
    }
