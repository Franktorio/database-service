import asyncio
import json
import pathlib
import threading
import time

from src.models.crud.system.auth_cookie_crud import revoke_expired_auth_cookies
from src.models.database import SessionLocal
from src.services.logging import log_message

PRINT_PREFIX = "COOKIE EXPIRY SERVICE"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
).get("cookie_expiry", {})

COOKIE_EXPIRY_SERVICE_ENABLED = LOCALCONFIG.get("enabled", True)
COOKIE_EXPIRY_SWEEP_INTERVAL = LOCALCONFIG.get("sweep_interval", 60)


async def _revoke_expired_auth_cookies_with_service_session() -> int:
    async with SessionLocal() as session:
        return await revoke_expired_auth_cookies(session=session)


def _cookie_expiry_loop() -> None:
    log_message(
        f"[INFO] [{PRINT_PREFIX}] Cookie expiry revocation loop started. "
        f"interval={COOKIE_EXPIRY_SWEEP_INTERVAL}s"
    )
    while True:
        revoked = asyncio.run(_revoke_expired_auth_cookies_with_service_session())
        if revoked > 0:
            log_message(f"[DEBUG] [{PRINT_PREFIX}] Revoked {revoked} expired auth cookie rows.")
        time.sleep(COOKIE_EXPIRY_SWEEP_INTERVAL)


def start_cookie_expiry_service() -> None:
    if not COOKIE_EXPIRY_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Cookie expiry revocation service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting cookie expiry revocation service...")
    thread = threading.Thread(target=_cookie_expiry_loop, daemon=True, name="CookieExpiryService")
    thread.start()