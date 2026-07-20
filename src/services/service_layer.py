# ~/src/services/service_layer.py

from src.services.backup import start_backup_service as _start_backup_service
from src.services.cookieexpiry import start_cookie_expiry_service as _start_cookie_expiry_service
from src.services.dbhealthcheck import start_healthcheck_service as _start_healthcheck_service
from src.services.ipblockcache import start_ip_block_cache_service as _start_ip_block_cache_service
from src.services.ratelimitcache import start_ratelimit_cache_service as _start_ratelimit_cache_service
from src.services.logging import log_message

PRINT_PREFIX = "SERVICE LAYER"


def start_backup_service() -> None:
    _start_backup_service()


def start_healthcheck_service() -> None:
    _start_healthcheck_service()


def start_cookie_expiry_service() -> None:
    _start_cookie_expiry_service()


def start_ratelimit_cache_service() -> None:
    _start_ratelimit_cache_service()


def start_ip_block_cache_service() -> None:
    _start_ip_block_cache_service()


def start_all_services() -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting managed services...")
    start_backup_service()
    start_healthcheck_service()
    start_cookie_expiry_service()
    start_ratelimit_cache_service()
    start_ip_block_cache_service()
    log_message(f"[INFO] [{PRINT_PREFIX}] Managed services startup complete.")
