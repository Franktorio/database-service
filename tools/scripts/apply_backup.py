# ~/tools/scripts/apply_backup.py

import argparse
import asyncio

from src.services.system.dbhealthcheck import restore_from_backup
from src.services.system.logging import log_message

PRINT_PREFIX = "APPLY BACKUP SCRIPT"

# USAGE (on project root): python3 -m tools.scripts.apply_backup <backup_file>
# e.g., python3 -m tools.scripts.apply_backup backups/backup_20260721060614.sql

def _argparse_args():

    parser = argparse.ArgumentParser(
        prog="python3 -m tools.scripts.apply_backup",
        description="Apply a database backup from a specified file.",
    )
    parser.add_argument("backup_file", type=str, help="Name of the backup file to apply (must be in the 'backups' directory).")
    return parser.parse_args()

async def _run():
    args = _argparse_args()
    backup_file = args.backup_file

    log_message(f"[INFO] [{PRINT_PREFIX}] Applying backup from file: {backup_file}")
    restore_from_backup(backup_file)
    log_message(f"[INFO] [{PRINT_PREFIX}] Backup applied successfully.")
    
if __name__ == "__main__":
    asyncio.run(_run())