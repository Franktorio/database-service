from src.services.logging import log_message
# ~/src/api/config.py
# Configuration settings for the API service.

PRINT_PREFIX = "API CONFIG"

VIEW_LEVEL = 0
EDIT_LEVEL = 1
BULK_OPERATIONS_LEVEL = 2
ADMIN_LEVEL = 3
SUPER_ADMIN_LEVEL = 4

PERM_LEVEL_MAP = {
    VIEW_LEVEL: "VIEW",
    EDIT_LEVEL: "EDIT",
    BULK_OPERATIONS_LEVEL: "BULK_OPERATIONS",
    ADMIN_LEVEL: "ADMIN",
    SUPER_ADMIN_LEVEL: "SUPER_ADMIN",
}

log_message(f"[DEBUG] [{PRINT_PREFIX}] Permission levels loaded: {PERM_LEVEL_MAP}")
