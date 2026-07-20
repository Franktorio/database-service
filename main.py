# ~/main.py - Entry point of application
from src.services.logging import initialize_logging
from src.services.logging import log_message
initialize_logging()

PRINT_PREFIX = "MAIN"

def main():
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting database service bootstrap.")
    from src.services.service_layer import start_backup_service
    from src.services.service_layer import start_cookie_expiry_service
    from src.services.service_layer import start_healthcheck_service
    from src.services.service_layer import start_ip_block_cache_service
    from src.services.service_layer import start_ratelimit_cache_service
    from src.api.app import start_api_server

    log_message(f"[DEBUG] [{PRINT_PREFIX}] Initializing background services and database.")
    
    start_backup_service()
    start_healthcheck_service()
    start_cookie_expiry_service()
    start_ratelimit_cache_service()
    start_ip_block_cache_service()

    start_api_server()
    log_message(f"[INFO] [{PRINT_PREFIX}] API startup routine completed.")

if __name__ == "__main__":
    main()
