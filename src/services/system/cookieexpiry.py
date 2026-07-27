import asyncio

from config.settings import COOKIE_EXPIRY_SETTINGS
from src.models.crud.system.auth_cookie_crud import revoke_expired_auth_cookies
from src.models.database import SessionLocal
from src.services.system.logging import log_message

PRINT_PREFIX = "COOKIE EXPIRY SERVICE"

COOKIE_EXPIRY_SERVICE_ENABLED = COOKIE_EXPIRY_SETTINGS.enabled
COOKIE_EXPIRY_SWEEP_INTERVAL = COOKIE_EXPIRY_SETTINGS.sweep_interval


async def _revoke_expired_auth_cookies_with_service_session() -> int:
    async with SessionLocal() as session:
        return await revoke_expired_auth_cookies(session=session)


async def _cookie_expiry_loop() -> None:
    while True:
        await _revoke_expired_auth_cookies_with_service_session()
        await asyncio.sleep(COOKIE_EXPIRY_SWEEP_INTERVAL)

def is_cookie_expiry_service_enabled() -> bool:
    return COOKIE_EXPIRY_SERVICE_ENABLED


async def cookie_expiry_service_loop() -> None:
    if not COOKIE_EXPIRY_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Cookie expiry revocation service is disabled.")
        return
    await _cookie_expiry_loop()