# ~/src/services/ratelimitcache.py

import asyncio
import json
import threading
import time

from config.loader import PROJECT_ROOT
from src.security.api_security import cleanup_inactive_ratelimiters
from src.security.cookie_security import cleanup_inactive_cookie_ratelimiters
from src.security.password_security import cleanup_inactive_password_ratelimiters
from src.services.system.logging import log_message

PRINT_PREFIX = "RATELIMIT CACHE SERVICE"

LOCALCONFIG = json.loads(
    (PROJECT_ROOT / "config" / "service_config.json").read_text()
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

        if (removed_api + removed_password + removed_cookie) > 0:
            log_message(
                f"[DEBUG] [{PRINT_PREFIX}] Cleanup sweep removed "
                f"api_cache={removed_api}, password_cache={removed_password}, "
                f"cookie_cache={removed_cookie}."
            )
        time.sleep(RATELIMIT_CACHE_SWEEP_INTERVAL)


def _wait_for_db_ready(db_ready_signal) -> None:
    while True:
        if db_ready_signal.is_ready():
            break
        time.sleep(1)


def _wait_for_db_ready_and_start(db_ready_signal) -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Waiting for DB ready signal before starting ratelimit cache loop.")
    _wait_for_db_ready(db_ready_signal)
    log_message(f"[INFO] [{PRINT_PREFIX}] DB ready signal received. Starting ratelimit cache loop.")
    _ratelimit_cache_loop()


def start_ratelimit_cache_service(db_ready_signal=None) -> None:
    if not RATELIMIT_CACHE_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Ratelimit cache cleanup service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting ratelimit cache cleanup service...")
    thread_target = _ratelimit_cache_loop
    if db_ready_signal is not None:
        thread_target = lambda: _wait_for_db_ready_and_start(db_ready_signal)
    thread = threading.Thread(target=thread_target, daemon=True, name="RateLimitCacheService")
    thread.start()
