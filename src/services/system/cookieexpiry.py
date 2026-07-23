import asyncio
import json
import threading

from config.loader import PROJECT_ROOT
from src.models.crud.system.auth_cookie_crud import revoke_expired_auth_cookies
from src.models.database import SessionLocal
from src.services.system.logging import log_message

PRINT_PREFIX = "COOKIE EXPIRY SERVICE"

LOCALCONFIG = json.loads(
    (PROJECT_ROOT / "config" / "service_config.json").read_text()
).get("cookie_expiry", {})

COOKIE_EXPIRY_SERVICE_ENABLED = LOCALCONFIG.get("enabled", True)
COOKIE_EXPIRY_SWEEP_INTERVAL = LOCALCONFIG.get("sweep_interval", 60)


async def _revoke_expired_auth_cookies_with_service_session() -> int:
    async with SessionLocal() as session:
        return await revoke_expired_auth_cookies(session=session)


async def _cookie_expiry_loop() -> None:
    log_message(
        f"[INFO] [{PRINT_PREFIX}] Cookie expiry revocation loop started. "
        f"interval={COOKIE_EXPIRY_SWEEP_INTERVAL}s"
    )
    while True:
        revoked = await _revoke_expired_auth_cookies_with_service_session()
        if revoked > 0:
            log_message(f"[DEBUG] [{PRINT_PREFIX}] Revoked {revoked} expired auth cookie rows.")
        await asyncio.sleep(COOKIE_EXPIRY_SWEEP_INTERVAL)


async def _wait_for_db_ready(db_ready_signal) -> None:
    while True:
        if db_ready_signal.is_ready():
            break
        await asyncio.sleep(1)


async def _wait_for_db_ready_and_start(db_ready_signal) -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Waiting for DB ready signal before starting cookie expiry loop.")
    await _wait_for_db_ready(db_ready_signal)
    log_message(f"[INFO] [{PRINT_PREFIX}] DB ready signal received. Starting cookie expiry loop.")
    await _cookie_expiry_loop()


def start_cookie_expiry_service(db_ready_signal=None) -> None:
    if not COOKIE_EXPIRY_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Cookie expiry revocation service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting cookie expiry revocation service...")
    thread_target = lambda: asyncio.run(_cookie_expiry_loop())
    if db_ready_signal is not None:
        thread_target = lambda: asyncio.run(_wait_for_db_ready_and_start(db_ready_signal))
    thread = threading.Thread(target=thread_target, daemon=True, name="CookieExpiryService")
    thread.start()