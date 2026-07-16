# ~/src/services/dbhealthcheck.py
import os
import signal
import threading
import subprocess
import time
import pathlib
import json
from config.loader import (
    POSTGRESQL_DATABASE_NAME,
    POSTGRESQL_USERNAME,
    POSTGRESQL_PASSWORD,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
)

PRINT_PREFIX = "DBHEALTHCHECK"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
)["dbhealthchecker"]

HEALTHCHECK_ENABLED = LOCALCONFIG.get("enabled", True)
AUTO_ROLLOVER = LOCALCONFIG.get("auto_rollover", True)
SHUTDOWN_ON_FAILURE = LOCALCONFIG.get("shutdown_on_failure", True)
LENIENCY = LOCALCONFIG.get("leniency", 5)
INTERVAL = LOCALCONFIG.get("interval", 60)
BACKUP_DIR = pathlib.Path(
    LOCALCONFIG.get("backup_dir", "backups")
)

def _check_database_health():
    print(f"[DEBUG] [{PRINT_PREFIX}] Performing database health check using pg_isready.")
    command = [
        "pg_isready",
        "-U", POSTGRESQL_USERNAME,
        "-h", POSTGRESQL_HOST,
        "-p", POSTGRESQL_PORT,
        "-d", POSTGRESQL_DATABASE_NAME
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )

    print(f"[DEBUG] [{PRINT_PREFIX}] Healthcheck command exit code: {result.returncode}. Next check will be in {INTERVAL} seconds.")
    return result.returncode == 0

def _get_last_backup():
    backups = list(BACKUP_DIR.glob("backup_*.sql"))

    if not backups:
        return None

    latest_backup = max(
        backups,
        key=lambda p: p.stat().st_mtime
    )
    print(f"[DEBUG] [{PRINT_PREFIX}] Latest backup selected: {latest_backup.name}")
    return latest_backup
    
def restore_from_backup(backup_file):
    print(f"[INFO] [{PRINT_PREFIX}] Starting restore from backup file: {backup_file}")
    command = [
        "psql",
        "-U", POSTGRESQL_USERNAME,
        "-h", POSTGRESQL_HOST,
        "-p", POSTGRESQL_PORT,
        "-d", POSTGRESQL_DATABASE_NAME,
        "-f", str(backup_file)
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env={**os.environ, "PGPASSWORD": POSTGRESQL_PASSWORD}
    )

    if result.returncode != 0:
        print(f"[ERROR] [{PRINT_PREFIX}] Restore failed: {result.stderr.decode()}")
        return False
    print(f"[INFO] [{PRINT_PREFIX}] Restore completed successfully.")
    return True


def _shutdown_process(exit_code: int) -> None:
    print(f"[INFO] [{PRINT_PREFIX}] Shutting down process with exit code {exit_code}.")
    os.kill(os.getpid(), signal.SIGTERM)
        
def healthcheck_loop():
    failure_count = 0
    print(f"[DEBUG] [{PRINT_PREFIX}] Healthcheck loop started with interval={INTERVAL}s and leniency={LENIENCY}.")

    while True:
        if not _check_database_health():
            failure_count += 1
            print(f"[WARNING] [{PRINT_PREFIX}] Database health check failed ({failure_count}/{LENIENCY})")
            
            if failure_count >= LENIENCY:
                print(f"[ERROR] [{PRINT_PREFIX}] Database is unhealthy.")
                
                if AUTO_ROLLOVER:
                    last_backup = _get_last_backup()
                    if last_backup:
                        print(f"[INFO] [{PRINT_PREFIX}] Restoring from backup: {last_backup}")
                        restore_from_backup(last_backup)
                    else:
                        print(f"[ERROR] [{PRINT_PREFIX}] No backups available for restoration.")
                else:
                    print(f"[INFO] [{PRINT_PREFIX}] Auto-rollover is disabled. No restoration will be performed.")
                
                if SHUTDOWN_ON_FAILURE:
                    _shutdown_process(1)
        else:
            if failure_count > 0:
                print(f"[INFO] [{PRINT_PREFIX}] Database health recovered; resetting failure counter.")
            failure_count = 0  # Reset on success

        time.sleep(INTERVAL)
        
def start_healthcheck_service():
    if HEALTHCHECK_ENABLED:
        print(f"[INFO] [{PRINT_PREFIX}] Starting database health check service...")
        healthcheck_thread = threading.Thread(target=healthcheck_loop, daemon=True)
        healthcheck_thread.start()
        print(f"[DEBUG] [{PRINT_PREFIX}] Healthcheck thread started as daemon.")
    else:
        print(f"[INFO] [{PRINT_PREFIX}] Database health check service is disabled.")