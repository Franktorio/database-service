# ~/src/services/ratelimitcache.py

import json
import pathlib
import threading
import time

from src.security.api_security import cleanup_inactive_ratelimiters
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
        cleanup_inactive_ratelimiters(RATELIMIT_CACHE_MAX_INACTIVE_SECONDS)
        time.sleep(RATELIMIT_CACHE_SWEEP_INTERVAL)


def start_ratelimit_cache_service() -> None:
    if not RATELIMIT_CACHE_SERVICE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Ratelimit cache cleanup service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting ratelimit cache cleanup service...")
    thread = threading.Thread(target=_ratelimit_cache_loop, daemon=True, name="RateLimitCacheService")
    thread.start()
