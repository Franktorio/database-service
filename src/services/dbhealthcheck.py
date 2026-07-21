# ~/src/services/dbhealthcheck.py
import os
import signal
import threading
import subprocess
import asyncio
import time
import pathlib
import json
from config.loader import (
    POSTGRESQL_DATABASE_NAME,
    POSTGRESQL_USERNAME,
    POSTGRESQL_PASSWORD,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
    AsyncSessionLocal,
)
from sqlalchemy import text
from src.services.logging import log_message

PRINT_PREFIX = "DBHEALTHCHECK"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
)["dbhealthchecker"]

HEALTHCHECK_ENABLED = LOCALCONFIG.get("enabled", True)
AUTO_ROLLOVER = LOCALCONFIG.get("auto_rollover", True)
SHUTDOWN_ON_FAILURE = LOCALCONFIG.get("shutdown_on_failure", True)
LENIENCY = LOCALCONFIG.get("leniency", 5)
INTERVAL = LOCALCONFIG.get("interval", 60)
HEALTHCHECK_TIMEOUT_SECONDS = LOCALCONFIG.get("healthcheck_timeout_seconds", 30)
RESTORE_SUBPROCESS_TIMEOUT_SECONDS = LOCALCONFIG.get("restore_subprocess_timeout_seconds", 30)
BACKUP_DIR = pathlib.Path(
    LOCALCONFIG.get("backup_dir", "backups")
)


def get_last_backup():
    backups = list(BACKUP_DIR.glob("backup_*.sql"))

    if not backups:
        return None

    latest_backup = max(
        backups,
        key=lambda p: p.stat().st_mtime
    )
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Latest backup selected: {latest_backup.name}")
    return latest_backup

async def database_query_check():
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        return True

    except Exception as exc:
        log_message(
            f"[ERROR] [{PRINT_PREFIX}] Database query failed: {exc}"
        )
        return False
    
def restore_from_backup(backup_file):
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting restore from backup file: {backup_file}")
    command = [
        "psql",
        "-U", POSTGRESQL_USERNAME,
        "-h", POSTGRESQL_HOST,
        "-p", POSTGRESQL_PORT,
        "-d", POSTGRESQL_DATABASE_NAME,
        "-f", str(backup_file)
    ]
    subprocess.run(
        command,
        check=True,
        timeout=RESTORE_SUBPROCESS_TIMEOUT_SECONDS,
        env={
            **os.environ,
            "PGPASSWORD": POSTGRESQL_PASSWORD,
        },
    )
    
def remove_bad_backup(backup_file):
    """Moves a backup file to a 'bad_backups' directory for further inspection."""
    bad_backups_dir = BACKUP_DIR / "bad_backups"
    bad_backups_dir.mkdir(exist_ok=True)
    destination = bad_backups_dir / backup_file.name
    try:
        backup_file.rename(destination)
        log_message(f"[INFO] [{PRINT_PREFIX}] Moved bad backup file to: {destination}")
    except Exception as exc:
        log_message(f"[ERROR] [{PRINT_PREFIX}] Failed to move bad backup file {backup_file} to {destination}: {exc}")

def healthcheck_service():
    _healthy = True
    _restore_attempted = False


    log_message(f"[INFO] [{PRINT_PREFIX}] Starting database healthcheck service with interval {INTERVAL} seconds.")
    failure_count = 0

    while True:
        time.sleep((INTERVAL))
        try:
            check = asyncio.run(
                asyncio.wait_for(
                    database_query_check(),
                    timeout=HEALTHCHECK_TIMEOUT_SECONDS,
                )
            )
        except Exception as exc:
            log_message(f"[ERROR] [{PRINT_PREFIX}] Exception during database healthcheck: {exc}")
            check = False

        if not check:
            if _healthy:
                log_message(f"[WARNING] [{PRINT_PREFIX}] Database healthcheck just failed. Starting failure count.")
            else:
                log_message(f"[WARNING] [{PRINT_PREFIX}] Database healthcheck still failing. Failure count: {failure_count + 1}/{LENIENCY}")
            _healthy = False
            failure_count += 1
        else:
            if not _healthy:
                log_message(f"[INFO] [{PRINT_PREFIX}] Database healthcheck recovered. Resetting failure count.")
            _healthy = True
            _restore_attempted = False
            failure_count = 0

        if failure_count >= LENIENCY:

            if SHUTDOWN_ON_FAILURE:
                log_message(f"[CRITICAL] [{PRINT_PREFIX}] Maximum failure count reached. Shutting down.")
                os.kill(os.getpid(), signal.SIGINT)
            else:
                log_message(f"[ERROR] [{PRINT_PREFIX}] Maximum failure count reached. Auto-rollover is {'enabled' if AUTO_ROLLOVER else 'disabled'}.")
                if AUTO_ROLLOVER and not _restore_attempted:
                    try:
                        latest_backup = get_last_backup()
                        if latest_backup:
                            if latest_backup.stat().st_size == 0:
                                log_message(f"[ERROR] [{PRINT_PREFIX}] Latest backup file is empty. Cannot restore.")
                                remove_bad_backup(latest_backup)
                                continue
                            _restore_attempted = True
                            restore_from_backup(latest_backup)
                            
                        else:
                            log_message(f"[ERROR] [{PRINT_PREFIX}] No backup found for auto-rollover.")
                    except Exception as exc:
                        log_message(f"[ERROR] [{PRINT_PREFIX}] Exception during auto-rollover: {exc}")
                        log_message(f"[ERROR] [{PRINT_PREFIX}] Auto-rollover failed. Shutting down.")
                        os.kill(os.getpid(), signal.SIGINT)

def start_healthcheck_service():
    if not HEALTHCHECK_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Healthcheck service is disabled in configuration.")
        return
    
    log_message(f"[INFO] [{PRINT_PREFIX}] Starting database healthcheck service...")
    thread = threading.Thread(target=healthcheck_service, daemon=True, name="DBHealthCheckService")
    thread.start()