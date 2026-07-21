# ~/main.py - Entry point of application
from src.services.logging import initialize_logging
from src.services.logging import log_message
initialize_logging()

PRINT_PREFIX = "MAIN"

class DBReadySignal:
    """A simple signal class to indicate when the database is ready."""
    def __init__(self):
        self._ready = False

    def set_ready(self):
        self._ready = True

    def is_ready(self) -> bool:
        return self._ready

def main():
    for _ in range(5):
        log_message(f"{'#' * 30}")
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting database service bootstrap.")
    from src.services.service_layer import start_backup_service
    from src.services.service_layer import start_cookie_expiry_service
    from src.services.service_layer import start_healthcheck_service
    from src.services.service_layer import start_ip_block_cache_service
    from src.services.service_layer import start_ratelimit_cache_service
    from src.api.app import start_api_server

    log_message(f"[DEBUG] [{PRINT_PREFIX}] Initializing background services and database.")
    
    signal = DBReadySignal()
    
    start_backup_service(signal)
    start_healthcheck_service(signal)
    start_cookie_expiry_service(signal)
    start_ratelimit_cache_service(signal)
    start_ip_block_cache_service(signal)

    start_api_server(signal) # Also starts DB; Also becomes the main event loop for the application. Sets the signal to ready when DB is ready.
    log_message(f"[INFO] [{PRINT_PREFIX}] API startup routine concluded.")

if __name__ == "__main__":
    main()
