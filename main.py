# ~/main.py - Entry point of application
from src.services.system.logging import initialize_logging
from src.services.system.logging import log_message
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
    from src.api.app import start_api_server

    log_message(f"[DEBUG] [{PRINT_PREFIX}] Initializing background services and database.")
    
    signal = DBReadySignal()
    log_message(
        f"[INFO] [{PRINT_PREFIX}] Async services are managed by FastAPI lifespan tasks."
    )

    start_api_server(signal) # Also starts DB; also becomes the main event loop for the application.
    log_message(f"[INFO] [{PRINT_PREFIX}] API startup routine concluded.")

if __name__ == "__main__":
    main()
