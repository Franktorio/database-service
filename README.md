# Clean Database Service

A self-contained **FastAPI + PostgreSQL + Redis** backend that provides authentication, API-key management, user management, rate limiting, IP blocking, automated backups, and database health monitoring out of the box. It is designed as a foundation ("system layer") that application-specific features are built on top of.

> **Status:** Development codebase. No production data, clients, or applied migrations are tied to this repository — it is safe to experiment with, reset, and restructure.

---

## Table of Contents

- [What this is](#what-this-is)
- [Architecture at a glance](#architecture-at-a-glance)
- [Project layout](#project-layout)
- [Requirements](#requirements)
- [Getting started](#getting-started)
- [Configuration](#configuration)
- [Deployment topologies (single-node vs. split roles)](#deployment-topologies-single-node-vs-split-roles)
- [Running the service](#running-the-service)
- [Operational scripts](#operational-scripts)
- [Background services](#background-services)
- [Documentation](#documentation)
- [License](#license)

---

## What this is

The service exposes a small, opinionated **system API** for:

| Capability | Description |
|---|---|
| **API keys** | Create, list, patch, and delete API keys with tiered permission levels and per-key rate limits. |
| **Users** | Create, list, patch, and delete user accounts with role-based access, password rotation, and login rate limiting. |
| **Authentication** | Bearer API keys for service-to-service calls, and signed JWT cookies (with server-side revocation) for browser-style sessions. |
| **Abuse protection** | Redis-backed sliding-window rate limiting and automatic temporary IP blocking on abusive bursts. |
| **Reliability services** | Scheduled PostgreSQL backups, a database health checker with optional auto-restore, and expired-cookie cleanup — all running as supervised background asyncio tasks. |

Everything under `src/**/system` is meant to be treated as **infrastructure** — the intent is that new, product-specific functionality is added *alongside* it (new tables, new CRUD modules, new routers) rather than by modifying it. See [`docs/EXPANSION_GUIDE.md`](docs/EXPANSION_GUIDE.md) for a concrete walkthrough.

## Architecture at a glance

```mermaid
flowchart LR
    Client -->|HTTPS| Uvicorn[Uvicorn / FastAPI]
    Uvicorn --> IPBlock[IP Block Decorator]
    IPBlock --> Auth[API Key / Cookie Auth]
    Auth --> Routes[Route Handlers]
    Routes --> CRUD[CRUD Layer]
    CRUD --> PG[(PostgreSQL)]
    Auth <--> Redis[(Redis: rate limits, permission cache, IP blocks)]
    subgraph Background Tasks
        Backup[Backup Service]
        Health[DB Health Check]
        CookieExpiry[Cookie Expiry Sweep]
    end
    Backup --> PG
    Health --> PG
    CookieExpiry --> PG
```

Every request to a protected route passes through, in order: **IP block check → authentication/authorization → rate limiting → route handler → CRUD → database**. Rate limits, permission lookups, and IP blocks are all served from Redis so PostgreSQL is only touched on cache misses and writes.

## Project layout

```
config/                 Environment loading (config/loader.py) and service_config.json (tunable knobs)
main.py                 Process entry point; starts logging then the API server
src/
  api/
    app.py              FastAPI app, lifespan (DB init + background tasks), root/test routes
    config.py           Permission level constants
    models.py           Shared Pydantic request/response models
    system/
      api_db_endpoints/ API key admin routes  (/api/db/keys)
      user_db_endpoints/ User admin routes     (/api/db/users)
  models/
    base.py             Declarative dataclass Base with to_dict()/from_dict()
    database.py         Async engine, session factory, with_session decorator
    tables/system/      SQLAlchemy ORM models (User, ApiKey, AuthCookie)
    crud/system/        Async CRUD functions (the only layer that talks to the ORM)
  security/
    tokens.py           API key / password hashing, JWT issuing & verification
    ip_block.py         Redis-backed abusive-IP blocking decorator
    extract.py          Request header/cookie/IP extraction helpers
    validation/         api_security.py, cookie_security.py, password_security.py
  services/
    supervisor.py       Restart-with-backoff wrapper for background asyncio tasks
    system/
      logging.py        Queue + worker-thread logger (console + rotating file)
      backup.py          Scheduled pg_dump backups with retention
      dbhealthcheck.py   Periodic SELECT 1 checks, optional auto-restore-from-backup
      cookieexpiry.py    Periodic revocation of expired JWT cookie rows
      cache/             Redis client, rate-limit cache, permission cache, Lua scripts
migrations/             Alembic migration environment + versions
tools/
  scripts/              One-off operational scripts (bootstrap Postgres/Redis, generate keys, restore backups)
  tests/                Live, end-to-end HTTP test script against a running instance
docs/                   Engineering report, API/DB reference, expansion guide (this deliverable)
```

## Requirements

- Python **3.10+** (developed against 3.12)
- PostgreSQL 13+
- Redis 6+ (Lua `EVAL` scripting support)
- `pg_dump` / `psql` client binaries available on `PATH` (used by the backup and health-check services)

Python dependencies are pinned in [`requirements.txt`](requirements.txt).

## Getting started

```bash
# 1. Clone and enter the project
cd clean-database-service

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure the environment
cp config/.env.example config/.env
# edit config/.env: set real DB/Redis credentials and generate random
# values for API_KEY_PEPPER, PASSWORD_PEPPER, and JWT_SECRET

# 5. Provision PostgreSQL and Redis (Debian/Ubuntu hosts with sudo access)
python3 -m tools.scripts.setup_postgres
python3 -m tools.scripts.setup_redis

# 6. Apply database migrations
alembic upgrade head

# 7. Bootstrap a SUPER_ADMIN API key (required — the API refuses to mint
#    SUPER_ADMIN keys over HTTP)
python3 -m tools.scripts.generate_api_key 4 1000

# 8. Run the service
python3 main.py
```

The API listens on `API_PORT` (default `8000`). Visit `http://localhost:8000/docs` for the interactive OpenAPI/Swagger UI generated automatically by FastAPI.

## Configuration

All configuration is environment-driven via `config/.env` (loaded by [`config/loader.py`](config/loader.py); see [`config/.env.example`](config/.env.example) for the full list of variables) plus tunable operational knobs in [`config/service_config.json`](config/service_config.json) (backup interval/retention, health-check leniency, cache sweep intervals, subprocess timeouts).

Key safety behavior: in any `OPERATING_MODE` other than `development`, the app **refuses to start** (raises `RuntimeError`) if `POSTGRESQL_PASSWORD`, `API_KEY_PEPPER`, `PASSWORD_PEPPER`, `JWT_SECRET`, or `REDIS_PASSWORD` are left at their insecure default values.

## Deployment topologies (single-node vs. split roles)

By default (see [Getting started](#getting-started)) PostgreSQL, Redis, and the FastAPI app all run on **one** host — that's the intended shape for a $10 VPS and requires no extra steps. This repo can also be split across dedicated nodes (e.g. a managed-feeling setup with one Postgres box, one Redis box, and one or more application boxes). **What you install, enable, and run is different for each role** — pick the row that matches the node in front of you:

| Node role | Run `python3 main.py`? | Install on this node | Key `.env` / config settings |
|---|:---:|---|---|
| **PostgreSQL node** | ❌ Never | PostgreSQL server only, via `python3 -m tools.scripts.setup_postgres` (needs this repo + venv + `config/.env` present just to run that one-off script — nothing from the repo runs continuously here afterward). | Set `POSTGRESQL_*` to the credentials/port you want provisioned. `API_ENABLED` and every `service_config.json` toggle are irrelevant here — the Python app never runs on this node. |
| **Redis node** | ❌ Never | Redis server only, via `python3 -m tools.scripts.setup_redis` (same one-off-script caveat as above). | Set `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` to match. Never leave `REDIS_PASSWORD` at its placeholder once this is network-reachable. |
| **FastAPI / application node** | ✅ Yes — the only role that does | This repo + `pip install -r requirements.txt`, plus PostgreSQL/Redis **client** tools only (e.g. `sudo apt-get install postgresql-client redis-tools`) — full server packages are not needed here. | `API_ENABLED=true`; point `POSTGRESQL_HOST`/`REDIS_HOST` at the other nodes' private addresses; set every pepper/secret for real. This is also the **only** place `backup`/`dbhealthchecker`/`cookie_expiry` in `service_config.json` have any effect — see note below. |
| **All-in-one** (default, single $10 VPS) | ✅ Yes | Everything above, on one host. | Defaults already assume `localhost` for both `POSTGRESQL_HOST` and `REDIS_HOST` — no extra steps. |

**Important constraints when splitting roles — none of these are handled automatically:**

- **Background services follow the app process, not the database.** `backup`, `dbhealthchecker`, and `cookie_expiry` are started inside the FastAPI `lifespan` handler (see [Running the service](#running-the-service)), so they **only run on the node where `API_ENABLED=true` and `main.py` is actually running** — there is currently no standalone mode to run them without also starting the API server. Flipping their toggles in `service_config.json` on a Postgres-only or Redis-only node has no effect, because that code path never executes there.
- **Backups land on the application node's disk, not the database node's.** `pg_dump`/`psql` are invoked as local subprocesses on whichever node runs `main.py`, connecting out to `POSTGRESQL_HOST` — the resulting `.sql` files are written to `backups/` on that same (application) node. Plan retention and any off-box copy step accordingly (see [`docs/DATABASE.md`](docs/DATABASE.md)).
- **`setup_postgres.py` does not open PostgreSQL to the network.** It only sets the `port` in `postgresql.conf`; `listen_addresses` and `pg_hba.conf` are left at their (localhost-only) defaults. To let a separate application node connect, you must manually set `listen_addresses` (e.g. to the node's private IP or `*`), add a scoped entry to `pg_hba.conf` for the app node's IP/CIDR (`scram-sha-256`/`md5`), restart PostgreSQL, and open the firewall for that IP only — ideally over a private network/VPC or a WireGuard/SSH tunnel, never a public IP.
- **`setup_redis.py` does not open Redis to the network either.** It only sets `port` and `requirepass`; `redis.conf`'s default `bind 127.0.0.1 -::1` is untouched, so a remote application node cannot connect until you manually change `bind` (to a private IP, never `0.0.0.0` on a public interface) and restart. Redis carries rate-limit counters and cached permission payloads — keep it on a private network even with a password set.
- These per-role capacity assumptions differ from the single-node estimates in [`docs/ENGINEERING_REPORT.md`](docs/ENGINEERING_REPORT.md#concurrent-user-capacity-estimates--10-vps-single-node), which explicitly assumes everything is co-located on one box — splitting roles changes the bottleneck analysis (network latency to Postgres/Redis becomes a factor; CPU contention from `pg_dump`/PBKDF2 no longer competes with Postgres/Redis for the same core).

## Running the service

`main.py` initializes logging, then calls `start_api_server()`, which runs a single Uvicorn process (`uvicorn.run(app, ...)`) that also owns the asyncio event loop used by all background services. On startup, the FastAPI `lifespan` handler:

1. Verifies database connectivity (`SELECT 1`).
2. Starts the backup, health-check, and cookie-expiry loops (each wrapped in a `TaskSupervisor` that restarts on failure with exponential backoff), if enabled in `service_config.json`.
3. Signals readiness so background services that were started outside the API process can begin.

On shutdown, background tasks are cancelled, the Redis client is closed, and the database engine is disposed.

## Operational scripts

Run all scripts from the project root as modules (they rely on `src`/`config` being importable):

| Script | Purpose | Typical node |
|---|---|---|
| `python3 -m tools.scripts.setup_postgres` | Installs, starts, and configures a local PostgreSQL instance and application role/database (Debian/Ubuntu + systemd). | PostgreSQL node |
| `python3 -m tools.scripts.setup_redis` | Installs, starts, and password-protects a local Redis instance. | Redis node |
| `python3 -m tools.scripts.generate_api_key <level> <rate_limit>` | Mints a new API key directly against the database — the **only** way to create a `SUPER_ADMIN` (level 4) key. | Application node (needs DB access) |
| `python3 -m tools.scripts.apply_backup <backup_file>` | Restores the database from a specific `backups/*.sql` file (drops and recreates the database first). | Application node (where the backup file lives) |
| `python3 -m tools.tests.live_system_api_test` | End-to-end smoke test against a **running** instance; requires `SYSTEM_TEST_SUPER_ADMIN_KEY`. Not a unit test suite. | Anywhere with network access to the API |

## Background services

| Service | File | Enabled via | Behavior |
|---|---|---|---|
| Backup | `src/services/system/backup.py` | `service_config.json:backup.enabled` | Runs `pg_dump` on an interval, keeps the newest N backups (`retention`). |
| DB Health Check | `src/services/system/dbhealthcheck.py` | `service_config.json:dbhealthchecker.enabled` | Periodic connectivity probe; can auto-restore from the latest backup or shut the process down after repeated failures. |
| Cookie Expiry | `src/services/system/cookieexpiry.py` | `service_config.json:cookie_expiry.enabled` | Periodically marks expired `auth_cookies` rows as revoked. |

All three are wrapped by [`TaskSupervisor`](src/services/supervisor.py), which restarts a crashed loop with exponential backoff up to a configurable attempt limit.

## Documentation

Detailed, deep-dive documentation lives in [`docs/`](docs/):

- **[`docs/ENGINEERING_REPORT.md`](docs/ENGINEERING_REPORT.md)** — A critical, category-by-category engineering audit of this codebase against industry practice, including concurrent-user capacity estimates on a $10 VPS.
- **[`docs/API.md`](docs/API.md)** — Full reference for every HTTP endpoint (auth, request/response shapes, status codes).
- **[`docs/DATABASE.md`](docs/DATABASE.md)** — Schema reference, SQLAlchemy conventions, migration workflow.
- **[`docs/EXPANSION_GUIDE.md`](docs/EXPANSION_GUIDE.md)** — How to add new, product-specific features (tables, CRUD, routes) without touching the `system` layer.

## License

[MIT](LICENSE) — Copyright (c) 2026 Nightfall Development Group.
