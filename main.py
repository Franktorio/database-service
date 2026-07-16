# ~/main.py - Entry point of application
from src.services.logging import initialize_logging
initialize_logging()

PRINT_PREFIX = "MAIN"

def main():
    print(f"[INFO] [{PRINT_PREFIX}] Starting database service bootstrap.")
    from src.services.backup import start_backup_service
    from src.services.dbhealthcheck import start_healthcheck_service
    from src.api.app import start_api_server

    print(f"[DEBUG] [{PRINT_PREFIX}] Initializing background services and database.")
    
    start_backup_service()
    start_healthcheck_service()

    start_api_server()
    print(f"[INFO] [{PRINT_PREFIX}] API startup routine completed.")

if __name__ == "__main__":
    main()