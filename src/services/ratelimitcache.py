# ~/src/services/ratelimitcache.py

import asyncio
import json
import pathlib
import threading
import time

from src.models.crud.system.auth_cookie_crud import delete_expired_auth_cookies
from src.security.api_security import cleanup_inactive_ratelimiters
from src.security.cookie_security import cleanup_inactive_cookie_ratelimiters
from src.security.password_security import cleanup_inactive_password_ratelimiters
from src.services.logging import log_message

PRINT_PREFIX = "RATELIMIT CACHE SERVICE"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
).get("ratelimit_cache", {})

RATELIMIT_CACHE_SERVICE_ENABLED = LOCALCONFIG.get("enabled", True)
RATELIMIT_CACHE_SWEEP_INTERVAL = LOCALCONFIG.get("sweep_interval", 60)
RATELIMIT_CACHE_MAX_INACTIVE_SECONDS = LOCALCONFIG.get("max_inactive_seconds", 900)


def _ratelimit_cache_loop() -> None:
    log_message(
        f"[INFO] [{PRINT_PREFIX}] Ratelimit cache cleanup loop started. "
        f"interval={RATELIMIT_CACHE_SWEEP_INTERVAL}s max_inactive={RATELIMIT_CACHE_MAX_INACTIVE_SECONDS}s"
    )
    while True:
        removed_api = cleanup_inactive_ratelimiters(RATELIMIT_CACHE_MAX_INACTIVE_SECONDS)
        removed_password = cleanup_inactive_password_ratelimiters() # This cleanup uses another default time
        removed_cookie = cleanup_inactive_cookie_ratelimiters(RATELIMIT_CACHE_MAX_INACTIVE_SECONDS)
        removed_expired_cookie_rows = asyncio.run(delete_expired_auth_cookies())

        if (removed_api + removed_password + removed_cookie + removed_expired_cookie_rows) > 0:
            log_message(
                f"[DEBUG] [{PRINT_PREFIX}] Cleanup sweep removed "
                f"api_cache={removed_api}, password_cache={removed_password}, "
                f"cookie_cache={removed_cookie}, expired_cookie_rows={removed_expired_cookie_rows}."
            )
        time.sleep(RATELIMIT_CACHE_SWEEP_INTERVAL)


def start_ratelimit_cache_service() -> None:
    if not RATELIMIT_CACHE_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Ratelimit cache cleanup service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting ratelimit cache cleanup service...")
    thread = threading.Thread(target=_ratelimit_cache_loop, daemon=True, name="RateLimitCacheService")
    thread.start()
