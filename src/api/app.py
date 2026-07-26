# ~/src/api/app.py

import asyncio
import uvicorn
import fastapi
from fastapi import Request
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from typing import Any

from config.loader import API_ENABLED, API_EXPOSE_TEST_ENDPOINTS, API_PORT, TRUSTED_PROXIES
from src.api.system.api_db_endpoints import routes as api_db_routes
from src.api.system.user_db_endpoints import routes as user_db_routes
from src.services.system.cache.redis.client import RedisClient


from src.security.validation.api_security import api_authentication
from src.security.ip_block import with_ip_block
from src.security.validation.password_security import auth_and_grant_token
from src.security.validation.cookie_security import cookie_authentication
from src.security.tokens import get_cookie_settings
from src.models.database import init_db, close_db
from src.services.system.cookieexpiry import (
    cookie_expiry_service_loop,
    is_cookie_expiry_service_enabled,
)
from src.services.system.dbhealthcheck import (
    healthcheck_service_loop,
    is_healthcheck_service_enabled,
)

from src.api.config import VIEW_LEVEL

from src.api.models import LoginRequestBase
from src.services.system.logging import log_message

PRINT_PREFIX = "API APP"

_DB_READY_SIGNAL: Any = None

TEST_DEFAULTS = {
    "expiration_minutes": 10,  # Token valid for 10 minutes; only for testing purposes
}

@asynccontextmanager
async def lifespan(app: fastapi.FastAPI):
    background_tasks: list[asyncio.Task] = []

    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan startup started.")
    await init_db()

    if is_healthcheck_service_enabled():
        background_tasks.append(asyncio.create_task(healthcheck_service_loop(), name="db-healthcheck-service"))
    if is_cookie_expiry_service_enabled():
        background_tasks.append(asyncio.create_task(cookie_expiry_service_loop(), name="cookie-expiry-service"))

    if background_tasks:
        log_message(f"[INFO] [{PRINT_PREFIX}] Started {len(background_tasks)} async background task(s).")

    if _DB_READY_SIGNAL is not None:
        _DB_READY_SIGNAL.set_ready()
        log_message(f"[INFO] [{PRINT_PREFIX}] DB ready signal set to ready.")
    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan startup complete.")

    yield # Application waits here while running, then resumes after shutdown.

    log_message(f"[INFO] [{PRINT_PREFIX}] API lifespan shutdown complete... performing cleanup.")
    for task in background_tasks:
        task.cancel()
    if background_tasks:
        await asyncio.gather(*background_tasks, return_exceptions=True)
        log_message(f"[INFO] [{PRINT_PREFIX}] Async background tasks stopped.")
    await RedisClient.close()
    await close_db()

app = fastapi.FastAPI(
    lifespan=lifespan
)
app.include_router(api_db_routes.router)
app.include_router(user_db_routes.router)
test_router = fastapi.APIRouter()

def start_api_server(db_ready_signal=None):
    """Start the API server using Uvicorn."""
    global _DB_READY_SIGNAL
    _DB_READY_SIGNAL = db_ready_signal
    if not API_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] API server is disabled in the configuration.")
        return
    log_message(
        f"[DEBUG] [{PRINT_PREFIX}] Registered router tags: "
        f"{api_db_routes.router.tags + user_db_routes.router.tags}"
    )
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting API server on port {API_PORT}...")
    uvicorn.run(app, host="0.0.0.0", port=API_PORT, forwarded_allow_ips=",".join(TRUSTED_PROXIES))
    

@app.get("/")
@with_ip_block
async def root(request: Request):
    """Root endpoint for the API service; returns a simple greeting message."""
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Root endpoint called.")
    return {"message": "Hello from the backend!"}

@test_router.post("/api-auth-test")
@with_ip_block
@api_authentication(permission_level=VIEW_LEVEL)
async def auth_test(request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Auth test endpoint called.")
    return {
        "message": f"API key is valid: {request.state.api_data}"
    }

@test_router.post("/login-auth-test")
@with_ip_block
async def login_test(login_request: LoginRequestBase, request: Request,):
    log_message(
        f"[DEBUG] [{PRINT_PREFIX}] Login test endpoint called for user: {login_request.username}."
    )

    token, _ = await auth_and_grant_token(
        username=login_request.username,
        password=login_request.password,
        ip_address=request.client.host if request.client else None,
        expiration=TEST_DEFAULTS["expiration_minutes"], # Token valid for 10 minutes; only for testing purposes
    )
    
    response = JSONResponse(content={"message": "Login successful."})
    response.set_cookie(**get_cookie_settings(expires_minutes=TEST_DEFAULTS["expiration_minutes"]), value=token)
    
    return response

@test_router.post("/cookie-auth-test")
@with_ip_block
@cookie_authentication()
async def cookie_test(request: Request):
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Cookie auth test endpoint called.")
    response = JSONResponse(content={"message": "Cookie authentication successful."})
    return response


if API_EXPOSE_TEST_ENDPOINTS:
    app.include_router(test_router)
    log_message(f"[INFO] [{PRINT_PREFIX}] Test/auth utility endpoints are enabled.")
else:
    log_message(f"[INFO] [{PRINT_PREFIX}] Test/auth utility endpoints are disabled.")