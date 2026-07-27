# Database Service

Async FastAPI + PostgreSQL service for small-scale administrative database operations. The current codebase provides:

- API-key-protected system administration endpoints.
- User account CRUD with password hashing and cookie-based login.
- Redis-backed token-bucket rate limiting for API keys, login attempts, cookie sessions, and IP blocking (with in-process cache wrappers).
- Background backup, cookie-expiry cleanup, and DB healthcheck services.
- PostgreSQL bootstrap and schema-migration helper scripts.

## What It Actually Contains

System tables currently managed by the service:

- `users`
- `api_keys`
- `auth_cookies`

Important index coverage:

- `users.username` via unique constraint.
- `api_keys.key_hash` via unique constraint.
- `api_keys.created_at` explicit index.
- `auth_cookies.token_hash` via unique constraint.
- `auth_cookies.username` explicit index.
- `auth_cookies(expires_at, revoked)` explicit composite index.

## Technology Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy async + asyncpg
- PostgreSQL

## Runtime Architecture

Startup flow today:

1. Logging is initialized in `main.py`.
2. Backup daemon thread is started and waits for DB ready signal.
3. Uvicorn starts the FastAPI app.
4. During API lifespan startup, the app verifies DB connectivity.
5. Async service loops (DB healthcheck and cookie expiry) start as FastAPI lifespan tasks on the same event loop when enabled.

Primary code areas:

- `main.py`: process entrypoint.
- `config/loader.py`: environment loading and secret safety checks.
- `config/service_config.json`: service intervals, retention, and timeouts.
- `src/api`: app registration, request models, and admin route surfaces.
- `src/models`: SQLAlchemy base, DB engine, table models, CRUD helpers.
- `src/security`: API key auth, cookie auth, password auth, token utilities, IP blocking, rate limiting.
- `src/services`: backup, DB healthcheck, cookie-expiry sweep, logging, and cache helpers.
- `tools/scripts`: PostgreSQL setup, Redis setup, API key bootstrap, schema migration, and backup apply utilities.

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
- `API_EXPOSE_TEST_ENDPOINTS`
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
- `TRUSTED_PROXIES`
- `REDIS_HOST`
- `REDIS_PORT`
- `REDIS_PASSWORD`

IP blocking defaults (app-level):

- `IP_BLOCKING_ENABLED='true'`
- `IP_BLOCKING_THRESHOLD='200'`
- `IP_BLOCKING_TIME_WINDOW='15'`
- `IP_BLOCKING_DURATION='1800'`
- Default behavior: 200 requests within 15 seconds blocks that IP for 30 minutes.

Secret-safety behavior:

- In non-development mode, unsafe defaults for PostgreSQL password, API-key pepper, password pepper, JWT secret, and Redis password raise at startup.
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
  - `reparations_interval`
  - `backup_dir`
  - `healthcheck_timeout_seconds`
  - `restore_subprocess_timeout_seconds`
  - `max_restore_attempts`
- `setup_postgres`
  - `command_subprocess_timeout_seconds`
  - `probe_subprocess_timeout_seconds`
- `setup_redis`
  - `command_subprocess_timeout_seconds`
  - `probe_subprocess_timeout_seconds`
- `ratelimit_cache`
  - `enabled`
  - `sweep_interval`
  - `max_inactive_seconds`
- `cookie_expiry`
  - `enabled`
  - `sweep_interval`
- `ip_block_cache`
  - `enabled`
  - `sweep_interval`
  - `max_inactive_seconds`

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

Conditional test/auth utility endpoints (`API_EXPOSE_TEST_ENDPOINTS=true`):

- `POST /api-auth-test`
- `POST /login-auth-test`
- `POST /cookie-auth-test`

SUPER_ADMIN API-key-protected endpoints:

- `GET /api/db/keys`
- `POST /api/db/keys`
- `PATCH /api/db/keys/{key_hash}`
- `DELETE /api/db/keys/{key_hash}`
- `GET /api/db/users`
- `GET /api/db/users/{username}`
- `POST /api/db/users`
- `PATCH /api/db/users/{username}`
- `PATCH /api/db/users/{username}/password`
- `PATCH /api/db/users/{username}/login-rate-limit`
- `DELETE /api/db/users/{username}`

Important request-format note:

- All API-key-protected endpoints use `Authorization: Bearer <api_key>`.

## Utility Scripts

PostgreSQL setup:

```bash
python3 -m tools.scripts.setup_postgres
```

Redis setup:

```bash
python3 -m tools.scripts.setup_redis
```

Generate a bootstrap API key:

```bash
python3 -m tools.scripts.generate_api_key <permission_level> <rate_limit>
```

Run schema-first migration copy/swap:

```bash
python3 -m tools.scripts.migrate_db
```

Apply Alembic revisions:

```bash
alembic upgrade head
```

Apply a SQL backup file:

```bash
python3 -m tools.scripts.apply_backup <backup_file_path>
```

## Logging

- Console logging plus daily-rotated file logging through the shared logger in `src/services/system/logging.py`.
- Routine info/debug chatter is intentionally minimized in startup, request, and CRUD paths.
- Active file: `logs/db_service_logs.log`.
- Rotation: midnight.
- Retention: 7 rotated files.
- Development mode still enables debug-level output, but the codebase now uses that level more sparingly.

## Deployment Notes

This repository is currently optimized for a single-node Linux deployment. The included PostgreSQL setup flow assumes Debian/Ubuntu-style package management and `systemd`.

Reverse-proxy deployments should be configured carefully: trusted forwarding headers are only honored when the peer IP is listed in `TRUSTED_PROXIES`.

If you split the system into dedicated nodes, keep the same `config/.env` values on every node so the API, PostgreSQL, and Redis services all point at the same shared endpoints.

### Common Node Profiles

API node:

- Run `python3 main.py`.
- Keep `API_ENABLED=true`.
- Enable only the background services you actually want on that node.
- For a lean API-only node, set these in `config/service_config.json`:
  - `backup.enabled=false`
  - `dbhealthchecker.enabled=false`
  - `cookie_expiry.enabled=false`
  - `ratelimit_cache.enabled=false`
  - `ip_block_cache.enabled=false`

PostgreSQL node:

- Install PostgreSQL and run `python3 -m tools.scripts.setup_postgres`.
- Keep the database-related `POSTGRESQL_*` values the same as the API node expects.
- Do not enable the API runtime services on this node unless you also run the application there.

Redis node:

- Install Redis and run `python3 -m tools.scripts.setup_redis`.
- Keep the Redis connection values in `config/.env` aligned with the API node.
- Do not enable the API runtime services on this node unless you also run the application there.

Combined single-node deployment:

- Leave the default service flags enabled if you want the full all-in-one setup.
- This mode is the simplest option when PostgreSQL and Redis are local to the same machine as the API.

## Known Limitations

These are current design realities, not aspirational behavior:

- Ratelimits and IP blocks are Redis-backed, but they still depend on Redis availability and TTL alignment.
- Background services are supervised asyncio tasks rather than daemon threads.
- SQL echo is enabled only in development mode.
- The DB engine uses `NullPool`, which limits connection reuse.
- Healthcheck/restore still requires production hardening before enabling automatic recovery.

## Documentation

- API reference: `docs/API.md`
- Database reference: `docs/DB.md`
- Expansion pattern: `docs/API_DB_FORMAT.md`
- Full codebase review: `docs/ENGINEERING_REVIEW_2026-07-26.md`
