import asyncio
import json
import pathlib
import threading
import time

from src.models.crud.system.persistent_logs_crud import safe_add_persistent_log
from src.models.database import SessionLocal
from src.security.ip_block import cleanup_inactive_ip_blocks
from src.services.logging import log_message

PRINT_PREFIX = "IP BLOCK CACHE SERVICE"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
).get("ip_block_cache", {})

IP_BLOCK_CACHE_ENABLED = LOCALCONFIG.get("enabled", True)
IP_BLOCK_CACHE_SWEEP_INTERVAL = LOCALCONFIG.get("sweep_interval", 60)
IP_BLOCK_CACHE_MAX_INACTIVE_SECONDS = LOCALCONFIG.get("max_inactive_seconds", 900)


async def _persist_cleanup_log_with_service_session(removed: int) -> None:
    async with SessionLocal() as session:
        await safe_add_persistent_log(
            log_type="IP BLOCK",
            log_level="INFO",
            message=f"Removed {removed} stale IP block cache entries.",
            session=session,
        )


def _ip_block_cache_loop() -> None:
    log_message(
        f"[INFO] [{PRINT_PREFIX}] IP block cache cleanup loop started. "
        f"interval={IP_BLOCK_CACHE_SWEEP_INTERVAL}s max_inactive={IP_BLOCK_CACHE_MAX_INACTIVE_SECONDS}s"
    )
    while True:
        removed = cleanup_inactive_ip_blocks(IP_BLOCK_CACHE_MAX_INACTIVE_SECONDS)
        if removed > 0:
            log_message(f"[DEBUG] [{PRINT_PREFIX}] Removed {removed} stale IP cache entries.")
            asyncio.run(_persist_cleanup_log_with_service_session(removed))
        time.sleep(IP_BLOCK_CACHE_SWEEP_INTERVAL)


def start_ip_block_cache_service() -> None:
    if not IP_BLOCK_CACHE_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] IP block cache cleanup service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Starting IP block cache cleanup service...")
    thread = threading.Thread(target=_ip_block_cache_loop, daemon=True, name="IpBlockCacheService")
    thread.start()
