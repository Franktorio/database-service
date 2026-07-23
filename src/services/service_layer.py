# ~/src/services/service_layer.py

from src.services.system.backup import start_backup_service as _start_backup_service
from src.services.system.logging import log_message

PRINT_PREFIX = "SERVICE LAYER"


def start_backup_service(db_ready_signal=None) -> None:
    _start_backup_service(db_ready_signal)


def start_all_services(db_ready_signal=None) -> None:
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting managed services...")
    start_backup_service(db_ready_signal)
    log_message(
        f"[INFO] [{PRINT_PREFIX}] Async background services are started by FastAPI lifespan."
    )
    log_message(f"[INFO] [{PRINT_PREFIX}] Managed services startup complete.")
