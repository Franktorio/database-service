# ~/src/services/backup.py

import asyncio
import os
from datetime import datetime
from pathlib import Path
from config.loader import (
    PROJECT_ROOT,
    POSTGRESQL_DATABASE_NAME,
    POSTGRESQL_USERNAME,
    POSTGRESQL_PASSWORD,
    POSTGRESQL_HOST,
    POSTGRESQL_PORT,
)
from config.settings import BACKUP_SETTINGS
from src.services.system.logging import log_message

PRINT_PREFIX = "BACKUP"

INTERVAL = BACKUP_SETTINGS.interval
RETENTION = BACKUP_SETTINGS.retention
BACKUP_ENABLED = BACKUP_SETTINGS.enabled
BACKUP_DIR = Path(BACKUP_SETTINGS.backup_dir)
if not BACKUP_DIR.is_absolute():
    BACKUP_DIR = PROJECT_ROOT / BACKUP_DIR
SUBPROCESS_TIMEOUT_SECONDS = BACKUP_SETTINGS.subprocess_timeout_seconds


def _get_last_backup():
    backups = list(BACKUP_DIR.glob("backup_*.sql"))

    if not backups:
        return None

    latest_backup = max(
        backups,
        key=lambda p: p.stat().st_mtime
    )
    return latest_backup


async def _create_backup() -> bool:
    BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    timestamp = datetime.now().strftime(
        "%Y%m%d%H%M%S"
    )

    backup_file = BACKUP_DIR / f"backup_{timestamp}.sql"

    command = [
        "pg_dump",
        "-U", POSTGRESQL_USERNAME,
        "-h", POSTGRESQL_HOST,
        "-p", str(POSTGRESQL_PORT),
        POSTGRESQL_DATABASE_NAME,
        "-f", str(backup_file)
    ]

    env = os.environ.copy()
    env["PGPASSWORD"] = POSTGRESQL_PASSWORD

    process = await asyncio.create_subprocess_exec(
        *command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )

    try:
        stdout, stderr = await asyncio.wait_for(
            process.communicate(),
            timeout=SUBPROCESS_TIMEOUT_SECONDS,
        )
    except asyncio.TimeoutError:
        process.kill()
        await process.communicate()
        log_message(
            f"[ERROR] [{PRINT_PREFIX}] pg_dump timed out after {SUBPROCESS_TIMEOUT_SECONDS}s."
        )
        return False

    if process.returncode != 0:
        stderr_text = stderr.decode("utf-8", errors="replace").strip()
        stdout_text = stdout.decode("utf-8", errors="replace").strip()
        log_message(
            f"[ERROR] [{PRINT_PREFIX}] Failed: {stderr_text or stdout_text or 'pg_dump returned a non-zero exit status.'}"
        )
        return False


    log_message(f"[INFO] [{PRINT_PREFIX}] Created {backup_file.name}")
    return True



def _cleanup() -> None:
    backups = sorted(
        BACKUP_DIR.glob("backup_*.sql"),
        key=lambda p: p.stat().st_mtime,
        reverse=True
    )

    for old in backups[RETENTION:]:
        old.unlink()



async def _backup_service_loop() -> None:
    while True:
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
            if await _create_backup():
                _cleanup()
        await asyncio.sleep(INTERVAL)

async def _wait_for_db_ready(db_ready_signal) -> None:
    while True:
        if db_ready_signal.is_ready():
            break
        await asyncio.sleep(1)


async def _wait_for_db_ready_and_start(db_ready_signal) -> None:
    await _wait_for_db_ready(db_ready_signal)
    await _backup_service_loop()


def is_backup_service_enabled() -> bool:
    return BACKUP_ENABLED


async def backup_service_loop(db_ready_signal=None) -> None:
    if not BACKUP_ENABLED:
        log_message(f"[INFO] [{PRINT_PREFIX}] Backup service is disabled.")
        return

    log_message(f"[INFO] [{PRINT_PREFIX}] Backup service started.")
    if db_ready_signal is not None:
        await _wait_for_db_ready_and_start(db_ready_signal)
        return

    await _backup_service_loop()
