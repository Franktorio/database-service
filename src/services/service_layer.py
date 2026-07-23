# ~/src/services/service_layer.py

from src.services.system.backup import start_backup_service as _start_backup_service
from src.services.system.cookieexpiry import start_cookie_expiry_service as _start_cookie_expiry_service
from src.services.system.dbhealthcheck import start_healthcheck_service as _start_healthcheck_service
from src.services.system.cache.ratelimitcache import start_ratelimit_cache_service as _start_ratelimit_cache_service
from src.services.system.cache.ipblockcache import start_ip_block_cache_service as _start_ip_block_cache_service
from src.services.system.logging import log_message

PRINT_PREFIX = "SERVICE LAYER"


def start_backup_service(db_ready_signal=None) -> None:
    _start_backup_service(db_ready_signal)


def start_healthcheck_service(db_ready_signal=None) -> None:
    _start_healthcheck_service(db_ready_signal)


def start_cookie_expiry_service(db_ready_signal=None) -> None:
    _start_cookie_expiry_service(db_ready_signal)


def start_ratelimit_cache_service(db_ready_signal=None) -> None:
    _start_ratelimit_cache_service(db_ready_signal)

def start_ip_block_cache_service(db_ready_signal=None) -> None:
    _start_ip_block_cache_service(db_ready_signal)

def start_all_services(db_ready_signal=None) -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting managed services...")
    start_backup_service(db_ready_signal)
    start_healthcheck_service(db_ready_signal)
    start_cookie_expiry_service(db_ready_signal)
    start_ratelimit_cache_service(db_ready_signal)
    start_ip_block_cache_service(db_ready_signal)
    log_message(f"[INFO] [{PRINT_PREFIX}] Managed services startup complete.")
