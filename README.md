# Database Service

Async FastAPI + PostgreSQL service for storing and managing API keys and database-backed application data, with API-key auth, permission levels, rate limiting, backups, health checks, and migration tooling. This tool is made to quickly deploy an easy-to-expand API based database backend.

## What This Service Does

- exposes API-key administration endpoints under `/api/db/keys`
- stores API keys and any future database tables added through the expansion pattern
- validates API keys and enforces per-key rate limits
- rotates logs via monkeypatched `print`
- runs backup and DB healthcheck background services

## Stack

- Python 3.12
- FastAPI + Uvicorn
- SQLAlchemy async + asyncpg
- PostgreSQL

## Project Layout

- `main.py`: process bootstrap
- `config/loader.py`: env/config loading
- `src/api/`: API server, auth validation, rate limiting, and API-key admin routes
- `src/models/`: DB engine/session, ORM tables, CRUD operations
- `src/services/`: logging override, backups, DB health checks
- `scripts/`: migration and API-key utility scripts
- `docs/`: API/DB documentation and expansion format guide

## Configuration

Create `config/.env` (or copy from `config/.env.example`) and set:

- `OPERATING_MODE`
- `POSTGRESQL_DATABASE_NAME`
- `POSTGRESQL_USERNAME`
- `POSTGRESQL_PASSWORD`
- `POSTGRESQL_HOST`
- `POSTGRESQL_PORT`
- `API_ENABLED`
- `API_PORT`
- `API_KEY_PEPPER`

## Install and Run

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Start service:

```bash
python main.py
```

Service starts logging override first, then backup/healthcheck workers, then FastAPI.

## Utility Scripts

Initial PostgreSQL setup (Debian/Ubuntu): installs PostgreSQL, enables/starts the service, sets PostgreSQL to `POSTGRESQL_PORT`, creates/updates the user from `POSTGRESQL_USERNAME` and `POSTGRESQL_PASSWORD`, and creates the database from `POSTGRESQL_DATABASE_NAME` in `config/.env`.

```bash
python3 -m scripts.setup_postgres
```

Generate API key. Use permission level `4` only for the bootstrap SUPER_ADMIN key:

```bash
python3 -m scripts.generate_api_key <permission_level> <rate_limit>
```

Database migration (schema-first compatibility copy/swap):

```bash
python3 -m scripts.migrate_db
```

## Logging Standard

All logs use monkeypatched print with level and prefix format:

- `[DEBUG] [PREFIX] ...`
- `[INFO] [PREFIX] ...`
- `[WARNING] [PREFIX] ...`
- `[ERROR] [PREFIX] ...`

## Documentation

- API reference: `docs/API.md`
- Database reference: `docs/DB.md`
- Consistent expansion format: `docs/API_DB_FORMAT.md`

## Notes

- API-protected routes require `api_key` in request body.
- Permission and rate-limit checks are enforced by `with_validation`.
- SQLAlchemy engine currently runs with `echo=True` in `src/models/database.py` for query visibility.
