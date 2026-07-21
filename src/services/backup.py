# ~/src/services/backup.py

import threading
import subprocess
import time
import pathlib
import json
import os
from datetime import datetime
from config.loader import (
    POSTGRESQL_DATABASE_NAME,
    POSTGRESQL_USERNAME,
    POSTGRESQL_PASSWORD,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
)
from src.services.logging import log_message

PRINT_PREFIX = "BACKUP"

LOCALCONFIG = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "config" / "service_config.json").read_text()
)["backup"]


INTERVAL = LOCALCONFIG.get("interval", 3600)
RETENTION = LOCALCONFIG.get("retention", 7)
BACKUP_ENABLED = LOCALCONFIG.get("enabled", True)
BACKUP_DIR = pathlib.Path(
    LOCALCONFIG.get("backup_dir", "backups")
)
SUBPROCESS_TIMEOUT_SECONDS = LOCALCONFIG.get("subprocess_timeout_seconds", 30)


def _get_last_backup():
    backups = list(BACKUP_DIR.glob("backup_*.sql"))

    if not backups:
        return None

    latest_backup = max(
        backups,
        key=lambda p: p.stat().st_mtime
    )
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Latest backup detected: {latest_backup.name}")
    return latest_backup


def _create_backup():
    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    backup_file = BACKUP_DIR / f"backup_{timestamp}.sql"
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Running pg_dump for backup target {backup_file}")

    command = [
        "pg_dump",
        "-U", POSTGRESQL_USERNAME,
        "-h", POSTGRESQL_HOST,
        "-p", POSTGRESQL_PORT,
        POSTGRESQL_DATABASE_NAME,
        "-f", str(backup_file)
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRESQL_PASSWORD

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            env=env,
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired:
        log_message(
            f"[ERROR] [{PRINT_PREFIX}] pg_dump timed out after {SUBPROCESS_TIMEOUT_SECONDS}s."
        )
        return False

    if result.returncode != 0:
        log_message(f"[ERROR] [{PRINT_PREFIX}] Failed: {result.stderr}")
        return False


    log_message(f"[INFO] [{PRINT_PREFIX}] Created {backup_file.name}")
    return True



def _cleanup():
    backups = sorted(
        BACKUP_DIR.glob("backup_*.sql"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old in backups[RETENTION:]:
        old.unlink()

        log_message(f"[INFO] [{PRINT_PREFIX}] Removed {old.name}")
    log_message(f"[DEBUG] [{PRINT_PREFIX}] Cleanup completed with retention={RETENTION}.")



def _backup_service():
    while True:
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Backup service running; checking for backup necessity.")
        last_backup = _get_last_backup()
        should_backup = False

        if last_backup is None:
            should_backup = True

        else:
            age = (
                datetime.now()
                -
                datetime.fromtimestamp(
                    last_backup.stat().st_mtime
                )
            )
            if age.total_seconds() >= INTERVAL:
                should_backup = True

        if should_backup:
            log_message(f"[DEBUG] [{PRINT_PREFIX}] Backup window reached; creating a new backup.")

            if _create_backup():
                _cleanup()
        else:
            log_message(f"[DEBUG] [{PRINT_PREFIX}] Backup skipped; most recent backup is within interval.")
        log_message(f"[DEBUG] [{PRINT_PREFIX}] Backup service sleeping for {INTERVAL} seconds.")
        time.sleep(INTERVAL)

def _wait_for_db_ready(db_ready_signal):
    while True:
        if db_ready_signal.is_ready():
            break
        time.sleep(1)


def _wait_for_db_ready_and_start(db_ready_signal):
    log_message(f"[INFO] [{PRINT_PREFIX}] Waiting for DB ready signal before starting backup loop.")
    _wait_for_db_ready(db_ready_signal)
    log_message(f"[INFO] [{PRINT_PREFIX}] DB ready signal received. Starting backup loop.")
    _backup_service()


def start_backup_service(db_ready_signal=None):
    if BACKUP_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Starting backup service...")
        thread_target = _backup_service
        if db_ready_signal is not None:
            thread_target = lambda: _wait_for_db_ready_and_start(db_ready_signal)
        thread = threading.Thread(
            target=thread_target,
            daemon=True
        )
        thread.start()
    else:
        log_message(f"[INFO] [{PRINT_PREFIX}] Backup service is disabled.")
