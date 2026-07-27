# ~/config/settings.py
# Typed, validated configuration for the tunable operational knobs in
# config/service_config.json.
#
# This replaces the pattern where each module (backup.py, dbhealthcheck.py,
# cookieexpiry.py, setup_postgres.py, setup_redis.py, cache_invalidation.py)
# independently ran json.loads(Path(...).read_text()) and pulled values out
# with untyped .get(...) calls. The JSON file is now read and validated
# exactly once, here, into one Pydantic model per top-level section. Every
# other module imports its settings instance from this file instead.

import json

from pydantic import BaseModel, Field

from config.loader import PROJECT_ROOT

SERVICE_CONFIG_PATH = PROJECT_ROOT / "config" / "service_config.json"


class BackupSettings(BaseModel):
    """Scheduled PostgreSQL backup service (src/services/system/backup.py)."""

    enabled: bool = Field(
        default=True,
        description="Whether the scheduled backup loop runs at all.",
    )
    interval: int = Field(
        default=3600,
        ge=1,
        description=(
            "Seconds between backup-due checks. A new backup is taken once the "
            "newest existing backup file is older than this many seconds."
        ),
    )
    retention: int = Field(
        default=7,
        ge=1,
        description="Number of most-recent backup files to keep; older ones are deleted after each successful backup.",
    )
    backup_dir: str = Field(
        default="backups",
        description="Directory to write .sql backup files into. Relative paths are resolved against the project root.",
    )
    subprocess_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Max seconds to wait for the pg_dump subprocess before killing it and treating the backup as failed.",
    )


class DbHealthCheckerSettings(BaseModel):
    """Database health-check / auto-recovery service (src/services/system/dbhealthcheck.py).

    This module is intended as a kill-on-failure safety net for deployments
    without 24/7 human monitoring - read every field's description carefully
    before changing defaults, especially `auto_rollover`.
    """

    enabled: bool = Field(
        default=True,
        description="Whether the periodic database health-check loop runs at all.",
    )
    auto_rollover: bool = Field(
        default=False,
        description=(
            "If true, automatically drop and restore the database from the latest "
            "backup after repeated health-check failures. This is destructive: it "
            "can discard every write made since the last backup. Disabled by default."
        ),
    )
    shutdown_on_failure: bool = Field(
        default=True,
        description=(
            "If true, the process sends itself SIGINT as a last resort once recovery "
            "options are exhausted (or immediately, if auto_rollover is disabled and "
            "failures persist past `leniency`)."
        ),
    )
    leniency: int = Field(
        default=5,
        ge=1,
        description="Number of consecutive failed health checks tolerated before triggering auto_rollover/shutdown_on_failure.",
    )
    interval: int = Field(
        default=60,
        ge=1,
        description="Seconds between health checks under normal (healthy) operation.",
    )
    reparations_interval: int = Field(
        default=5,
        ge=1,
        description="Seconds between health checks while recovering right after a restore, before resuming the normal `interval`.",
    )
    healthcheck_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Max seconds to wait for a single health-check query before treating it as failed.",
    )
    restore_subprocess_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Max seconds to wait for each psql/pg_dump subprocess invoked during a restore.",
    )
    max_restore_attempts: int = Field(
        default=3,
        ge=1,
        description="Max number of distinct backups to try restoring from before giving up and shutting down.",
    )
    backup_dir: str = Field(
        default="backups",
        description=(
            "Directory to read backups from and quarantine failed ones into "
            "(as backup_dir/bad_backups/...). Relative paths are resolved against the project root."
        ),
    )


class SetupPostgresSettings(BaseModel):
    """One-off PostgreSQL provisioning script (tools/scripts/setup_postgres.py)."""

    command_subprocess_timeout_seconds: int = Field(
        default=60,
        ge=1,
        description="Max seconds to wait for privileged setup commands (apt-get, systemctl, psql DDL) before failing.",
    )
    probe_subprocess_timeout_seconds: int = Field(
        default=60,
        ge=1,
        description="Max seconds to wait for read-only probe commands (e.g. checking existing config) before failing.",
    )


class SetupRedisSettings(BaseModel):
    """One-off Redis provisioning script (tools/scripts/setup_redis.py)."""

    command_subprocess_timeout_seconds: int = Field(
        default=60,
        ge=1,
        description="Max seconds to wait for privileged setup commands (apt-get, systemctl) before failing.",
    )
    probe_subprocess_timeout_seconds: int = Field(
        default=30,
        ge=1,
        description="Max seconds to wait for the redis-cli PING verification probe before failing.",
    )


class CookieExpirySettings(BaseModel):
    """Expired auth-cookie revocation sweep (src/services/system/cookieexpiry.py)."""

    enabled: bool = Field(
        default=True,
        description="Whether the periodic expired-cookie revocation loop runs at all.",
    )
    sweep_interval: int = Field(
        default=60,
        ge=1,
        description="Seconds between sweeps that mark expired auth_cookies rows as revoked.",
    )


class RedisIndexPrefixes(BaseModel):
    """Domain prefixes used to namespace Redis keys (see src/models/crud/cache_invalidation.py)."""

    api_key: str = Field(
        default="api_key:",
        description="Prefix for API-key rate-limit/permission cache keys.",
    )
    cookie: str = Field(
        default="cookie:",
        description="Prefix for auth-cookie rate-limit cache keys.",
    )
    user: str = Field(
        default="user:",
        description="Prefix for user permission/role cache keys.",
    )
    password: str = Field(
        default="password:",
        description="Prefix for per-username login rate-limit cache keys.",
    )
    ip_block: str = Field(
        default="ip_block:",
        description="Prefix for per-IP burst-block cache keys.",
    )


class ServiceConfig(BaseModel):
    """Root model mirroring the full shape of config/service_config.json."""

    backup: BackupSettings = Field(default_factory=BackupSettings)
    dbhealthchecker: DbHealthCheckerSettings = Field(default_factory=DbHealthCheckerSettings)
    setup_postgres: SetupPostgresSettings = Field(default_factory=SetupPostgresSettings)
    setup_redis: SetupRedisSettings = Field(default_factory=SetupRedisSettings)
    cookie_expiry: CookieExpirySettings = Field(default_factory=CookieExpirySettings)
    redis_index_prefixes: RedisIndexPrefixes = Field(default_factory=RedisIndexPrefixes)


def _load_service_config() -> ServiceConfig:
    raw = json.loads(SERVICE_CONFIG_PATH.read_text())
    return ServiceConfig.model_validate(raw)


# Parsed and validated once at import time.
SERVICE_CONFIG: ServiceConfig = _load_service_config()

# One importable instance per section - e.g. `from config.settings import BACKUP_SETTINGS`.
BACKUP_SETTINGS: BackupSettings = SERVICE_CONFIG.backup
DBHEALTHCHECKER_SETTINGS: DbHealthCheckerSettings = SERVICE_CONFIG.dbhealthchecker
SETUP_POSTGRES_SETTINGS: SetupPostgresSettings = SERVICE_CONFIG.setup_postgres
SETUP_REDIS_SETTINGS: SetupRedisSettings = SERVICE_CONFIG.setup_redis
COOKIE_EXPIRY_SETTINGS: CookieExpirySettings = SERVICE_CONFIG.cookie_expiry
REDIS_INDEX_PREFIXES: RedisIndexPrefixes = SERVICE_CONFIG.redis_index_prefixes
