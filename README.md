# Database Service

Async FastAPI + PostgreSQL service for small-scale administrative database operations. The current codebase provides:

- API-key-protected system administration endpoints.
- User account CRUD with password hashing and cookie-based login.
- In-memory rate limiting for API keys, login attempts, cookie sessions, and IP blocking.
- Background backup, cookie-expiry cleanup, DB healthcheck, and cache cleanup services.
- PostgreSQL bootstrap and schema-migration helper scripts.

## What It Actually Contains

System tables currently managed by the service:

- `users`
- `api_keys`
- `auth_cookies`
- `persistent_logs`

Important index coverage:

- `users.username` via unique constraint.
- `api_keys.key_hash` via unique constraint.
- `api_keys.created_at` explicit index.
- `auth_cookies.token_hash` via unique constraint.
- `auth_cookies.username` explicit index.
- `auth_cookies(expires_at, revoked)` explicit composite index.
- `persistent_logs.created_at` explicit index.

## Technology Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy async + asyncpg
- PostgreSQL

## Runtime Architecture

Startup flow today:

1. Logging is initialized in `main.py`.
2. Background daemon threads are started for backup, DB healthcheck, cookie expiry, IP-block cache cleanup, and API-key ratelimit cache cleanup.
3. Uvicorn starts the FastAPI app.
4. During API lifespan startup, SQLAlchemy creates tables and now also creates any declared missing indexes with `checkfirst=True`.

Primary code areas:

- `main.py`: process entrypoint.
- `config/loader.py`: environment loading and secret safety checks.
- `config/service_config.json`: service intervals, retention, and timeouts.
- `src/api`: app registration, request models, and admin route surfaces.
- `src/models`: SQLAlchemy base, DB engine, table models, CRUD helpers.
- `src/security`: API key auth, cookie auth, password auth, token utilities, IP blocking, rate limiting.
- `src/services`: backup, DB healthcheck, cookie-expiry sweep, logging, cache cleanup.
- `scripts`: PostgreSQL setup, API key bootstrap, schema migration.

## Configuration

Create `config/.env` and set at minimum:

- `OPERATING_MODE`
- `POSTGRESQL_DATABASE_NAME`
- `POSTGRESQL_USERNAME`
- `POSTGRESQL_PASSWORD`
- `POSTGRESQL_HOST`
- `POSTGRESQL_PORT`
- `API_ENABLED`
- `API_PORT`
- `API_KEY_PEPPER`
- `PASSWORD_PEPPER`
- `JWT_SECRET`
- `JWT_ALGORITHM`
- `JWT_EXP_MINUTES`

Also supported:

- `API_KEY_TOKEN_BYTES`
- `PASSWORD_HASH_ITERATIONS`
- `PASSWORD_HASH_ALGORITHM`
- `LOGIN_ATTEMPTS_LIMIT`
- `LOGIN_TIME_WINDOW`
- `COOKIE_DEFAULT_RATE_LIMIT`
- `RATE_LIMIT_WINDOW_SECONDS`
- `IP_BLOCKING_ENABLED`
- `IP_BLOCKING_THRESHOLD`
- `IP_BLOCKING_TIME_WINDOW`
- `IP_BLOCKING_DURATION`

Secret-safety behavior:

- In non-development mode, unsafe defaults for PostgreSQL password, API-key pepper, password pepper, and JWT secret raise at startup.
- In development mode, those unsafe defaults only log warnings.

## Service Runtime Config

`config/service_config.json` currently controls:

- `backup`
  - `enabled`
  - `interval`
  - `retention`
  - `backup_dir`
  - `subprocess_timeout_seconds`
- `dbhealthchecker`
  - `enabled`
  - `auto_rollover`
  - `shutdown_on_failure`
  - `leniency`
  - `interval`
  - `backup_dir`
  - `healthcheck_subprocess_timeout_seconds`
  - `restore_subprocess_timeout_seconds`
- `setup_postgres`
  - `command_subprocess_timeout_seconds`
  - `probe_subprocess_timeout_seconds`
- `ratelimit_cache`
  - `enabled`
  - `sweep_interval`
  - `max_inactive_seconds`
- `cookie_expiry`
  - `enabled`
  - `sweep_interval`

## Running Locally

Install dependencies:

```bash
pip3 install -r requirements.txt
```

Start the service:

```bash
python3 main.py
```

## Live System API Test

The live end-to-end system API test is folder-based and covers all current API routes:

- `tools/tests/live_system_api_test.py`

Required environment variable:

- `SYSTEM_TEST_SUPER_ADMIN_KEY`

Base URL resolution:

- Uses `SYSTEM_TEST_BASE_URL` when set.
- Otherwise builds `http://127.0.0.1:<API_PORT>` from `config/.env`.

Run in current process:

```bash
python3 tools/tests/live_system_api_test.py
```

## Current API Surface

Public/test endpoints:

- `GET /`
- `POST /api-auth-test`
- `POST /login-auth-test`
- `POST /cookie-auth-test`
- `GET /api/db/keys/`

SUPER_ADMIN API-key-protected endpoints:

- `GET /api/db/keys/list`
- `POST /api/db/keys/create`
- `POST /api/db/keys/update`
- `DELETE /api/db/keys/delete`
- `GET /api/db/users/list`
- `GET /api/db/users/{username}`
- `POST /api/db/users/create`
- `PATCH /api/db/users/update`
- `PATCH /api/db/users/password`
- `PATCH /api/db/users/login-rate-limit`
- `DELETE /api/db/users/delete`

Important request-format note:

- All API-key-protected endpoints use `Authorization: Bearer <api_key>`.

## Utility Scripts

PostgreSQL setup:

```bash
python3 -m scripts.setup_postgres
```

Generate a bootstrap API key:

```bash
python3 -m scripts.generate_api_key <permission_level> <rate_limit>
```

Run schema-first migration copy/swap:

```bash
python3 -m scripts.migrate_db
```

## Logging

- Console logging plus daily-rotated file logging.
- Active file: `logs/db_service_logs.log`.
- Rotation: midnight.
- Retention: 7 rotated files.
- Development mode enables debug-level output.

## Deployment Notes

This repository is currently optimized for a single-node Linux deployment. The included PostgreSQL setup flow assumes Debian/Ubuntu-style package management and `systemd`.

Reverse-proxy deployments should be treated carefully because IP blocking currently uses `request.client.host` directly and does not parse trusted forwarding headers.

## Known Limitations

These are current design realities, not aspirational behavior:

- Ratelimits and IP blocks are process-local, not shared across instances.
- Background services are daemon threads rather than supervised workers.
- SQL echo is enabled only in development mode.
- The DB engine uses `NullPool`, which limits connection reuse.
- Healthcheck/restore still requires production hardening before enabling automatic recovery.

## Documentation

- API reference: `docs/API.md`
- Database reference: `docs/DB.md`
- Expansion pattern: `docs/API_DB_FORMAT.md`
- Full codebase review: `docs/CODEBASE_REPORT.md`
