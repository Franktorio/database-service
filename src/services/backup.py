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


def _get_last_backup():
    backups = list(BACKUP_DIR.glob("backup_*.sql"))

    if not backups:
        return None

    latest_backup = max(
        backups,
        key=lambda p: p.stat().st_mtime
    )
    print(f"[DEBUG] [{PRINT_PREFIX}] Latest backup detected: {latest_backup.name}")
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
    print(f"[DEBUG] [{PRINT_PREFIX}] Running pg_dump for backup target {backup_file}")

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

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        env=env
    )

    if result.returncode != 0:
        print(f"[ERROR] [{PRINT_PREFIX}] Failed: {result.stderr}")
        return False


    print(f"[INFO] [{PRINT_PREFIX}] Created {backup_file.name}")
    return True



def _cleanup():
    backups = sorted(
        BACKUP_DIR.glob("backup_*.sql"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old in backups[RETENTION:]:
        old.unlink()

        print(f"[INFO] [{PRINT_PREFIX}] Removed {old.name}")
    print(f"[DEBUG] [{PRINT_PREFIX}] Cleanup completed with retention={RETENTION}.")



def _backup_service():
    while True:
        print(f"[DEBUG] [{PRINT_PREFIX}] Backup service running; checking for backup necessity.")
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
            print(f"[DEBUG] [{PRINT_PREFIX}] Backup window reached; creating a new backup.")

            if _create_backup():
                _cleanup()
        else:
            print(f"[DEBUG] [{PRINT_PREFIX}] Backup skipped; most recent backup is within interval.")
        print(f"[DEBUG] [{PRINT_PREFIX}] Backup service sleeping for {INTERVAL} seconds.")
        time.sleep(INTERVAL)

def start_backup_service():
    if BACKUP_ENABLED:
        print(f"[INFO] [{PRINT_PREFIX}] Starting backup service...")
        thread = threading.Thread(
            target=_backup_service,
            daemon=True
        )
        thread.start()
    else:
        print(f"[INFO] [{PRINT_PREFIX}] Backup service is disabled.")