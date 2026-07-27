# Database Report

This document is a technical reference plus an operational audit of the current database layer. It reflects the live implementation, not just intended architecture.

## Report Metadata

- Date: 2026-07-23
- Scope: schema, initialization flow, CRUD behavior, services touching DB, migration and backup tooling
- Basis: current main branch at HEAD in this workspace
- Method: static code review across model, CRUD, security, service, and script layers

## Database Runtime Architecture

Database runtime is implemented with async SQLAlchemy over asyncpg.

Current behavior in practice:

- Engine is created once in src/models/database.py with postgresql+asyncpg.
- Connection pooling uses SQLAlchemy's default async pool with configured size, overflow, timeout, recycle, and pre-ping settings.
- Session factory is async_sessionmaker with expire_on_commit=False.
- SQL echo is enabled only when OPERATING_MODE is development.
- Schema changes are managed through Alembic revisions under migrations/versions; runtime init only verifies connectivity.

Operational implications:

- The configured pool trades off reuse, capacity, and liveness checks via pool_size, max_overflow, pool_timeout, pool_recycle, and pool_pre_ping.
- With frequent short DB operations (auth checks), per-request connect/disconnect overhead is non-trivial.
- Because expire_on_commit=False, ORM instances remain usable after commit without implicit refresh. This improves endpoint ergonomics, but stale-field assumptions can slip into multi-step flows if code reuses old objects.

## Startup and DB Readiness Sequencing

The startup design now combines a readiness gate with FastAPI lifespan-managed async tasks.

Observed sequence:

- main.py creates a DBReadySignal and starts the API server.
- API server starts via Uvicorn.
- FastAPI lifespan startup calls init_db().
- Lifespan then starts enabled async tasks such as backup, healthcheck, and cookie-expiry on the same event loop.
- DBReadySignal is set ready after DB initialization, allowing backup loop startup.

What this fixes:

- Async maintenance loops no longer run in separate threads with independent event loops.
- DB-dependent loops no longer race schema initialization at process startup.

Residual caveat:

- DBReadySignal is in-process memory only. This is fine for single-process operation but not meaningful across multiple worker processes or hosts.
- Service lifecycle is still mixed only in the sense that backup, healthcheck, and cookie-expiry are all app-managed async tasks that share the API process event loop.

## Schema Initialization Semantics

Schema initialization is handled outside the request path through Alembic. Runtime init_db in src/models/database.py only verifies connectivity.

Detailed behavior:

- Alembic revisions capture schema changes.

Why this matters:

- Schema changes are explicit and reviewable.
- Runtime startup no longer mutates schema objects.

Nitpicky notes:

- Alembic version tracking now provides the schema history ledger.
- init_db now does a simple connectivity check and emits only a single startup info log.

## Current Tables

### users

Purpose:

- Stores local identity data for password authentication.
- Stores role list and per-user password login rate-limit configuration.

Key fields and defaults:

- id: integer PK.
- username: unique, non-null.
- password_hash: non-null.
- password_salt: non-null, default empty string.
- hash_iterations: non-null, default 210000.
- hash_algorithm: non-null, default pbkdf2_sha256.
- email: nullable, default empty string.
- login_rate_limit: non-null, default 10.
- roles: ARRAY(String), non-null, default empty list.
- created_at: timezone-aware server_default now().
- last_updated_at: timezone-aware server_default now(), onupdate now().

Index and constraint posture:

- Unique index/constraint on username is the principal lookup accelerator.

Design caveats:

- roles uses PostgreSQL ARRAY and is therefore intentionally Postgres-specific.
- password_salt default empty string is safe only if every create/update path always supplies a real salt (current user-create path does, but DB-level default still allows bad rows from out-of-band SQL writes).

### api_keys

Purpose:

- Stores hashed API key identities and policy attributes used by API auth.

Key fields and defaults:

- id: integer PK.
- key_hash: unique, non-null.
- permission_level: non-null, default 0.
- rate_limit: non-null, default 1000.
- email: nullable, default empty string.
- created_at: timezone-aware server_default now(), indexed.
- last_updated_at: timezone-aware server_default now(), onupdate now().

Index and query alignment:

- Unique key_hash serves key lookup on auth cache miss.
- created_at index aligns with list endpoint ordering by created_at.

### auth_cookies

Purpose:

- Stores hashed JWT cookie identities for revocation checks and expiration maintenance.

Key fields:

- id: integer PK.
- token_hash: unique, non-null.
- username: non-null, indexed, FK to users.username (ON DELETE CASCADE).
- user_id: non-null, indexed, FK to users.id (ON DELETE CASCADE).
- expires_at: timezone-aware, non-null.
- revoked: non-null boolean, default false.
- created_at: timezone-aware server_default now().

Indexes:

- Unique token_hash.
- Single-column username index.
- Single-column user_id index.
- Composite index on expires_at, revoked.

Design notes:

- Cookie ownership now has database-enforced referential integrity via username and user_id FKs.
- ON DELETE CASCADE keeps auth_cookies consistent when a user row is removed.

### persistent_logs
This table and the associated persistent-log CRUD path were removed from the current codebase.

## CRUD and Transaction Conventions

Shared pattern across system CRUD modules:

- Each function accepts optional session: AsyncSession | None.
- If no session is passed, function creates SessionLocal and self-closes it.
- Most functions commit internally.

Strengths:

- Easy call sites and low boilerplate for single-operation requests.
- Explicit session injection allows composition where needed.

Important transactional caveat:

- Several helper functions commit even when participating in broader flows via shared session.
- Example: user update and user delete call delete_auth_cookies_by_username, which commits before subsequent user-row mutation/deletion.
- Consequence: operations that appear logically atomic can become split into multiple commit boundaries.

Why this is nitpicky but important:

- If a downstream step fails after an earlier helper commit, side effects may remain partially applied.
- For strict consistency semantics, compose with outer transaction control and avoid inner helper commits.

## Database Access Patterns in Security Paths

The auth stack is DB-coupled in specific places:

- API key auth:
	- Cache miss reads api_keys by key_hash.
	- Rate-limit state is persisted in Redis and accessed through local limiter wrappers.
- Password auth:
	- Reads users by username.
	- User-specific password ratelimit state is persisted in Redis.
- Cookie issuance:
	- New JWT hash is persisted in auth_cookies.

Operational implication:

- Auth paths still include both DB reads and Redis-backed state changes, so request latency is sensitive to cache misses and DB health.

## Background Services Touching the Database

### Cookie Expiry Service

- Periodically revokes expired auth_cookies rows.
- Uses a service-owned async session per sweep.
- Sweep interval is configurable in service_config.json.

### DB Healthcheck Service

- Runs SELECT 1 via SessionLocal.
- Tracks consecutive failures with leniency threshold.
- Can auto-rollover by restoring from latest backup when configured.

Recovery behavior details:

- Backup file zero-size check is present before restore.
- Failed restored backups can be quarantined into backups/bad_backups.
- Restore attempts are bounded by max_restore_attempts.

Risk notes:

- restore_from_backup drops and recreates the active DB before replay.
- No cryptographic integrity check or SQL sanity validation of backup contents is performed before destructive restore actions.

### Backup Service

- Uses pg_dump to write timestamped SQL files.
- Keeps only retention newest files.
- Uses readiness gate before entering loop.

Operational caveat:

- Backup success is based on subprocess return code; no replay verification is performed at backup creation time.

## Migration Behavior

tools/scripts/migrate_db.py implements a copy-and-swap migration strategy.

Workflow:

- Create temporary database.
- Materialize latest metadata schema in temp DB.
- For common table names between source and temp, copy rows using only exactly compatible columns by name and type.
- Rename original DB to backup name.
- Rename temp DB to production DB name.

Technical caveats:

- Column rename/type-change scenarios do not fail migration by default; incompatible fields are silently excluded from copy set.
- Sequence state reconciliation is not explicitly reset after ID copy.
- Data transforms are not represented; this is structural compatibility copy, not declarative migration semantics.
- Old database is retained with timestamped suffix, increasing rollback options but also requiring lifecycle cleanup policy.

## Configuration and Connectivity Notes

- Connection URL is built by direct string interpolation in config/loader.py.
- Credentials are not URL-encoded before DSN assembly.

Why this matters:

- Special characters in username/password can break DSN parsing unless encoded.

## Capacity and Scaling Characteristics

Current DB design assumptions are single-node and moderate load:

- Ratelimiter counters are Redis-backed; some resolver/block metadata remains process-local.
- The SQLAlchemy async pool settings favor predictable reuse and bounded growth over unbounded connection churn.
- Auth paths include both read and write DB activity (especially with persistent logs enabled).

Scaling caveat:

- Multiple app instances can share limiter counters through Redis, but temporary local block metadata still has per-process behavior.

## High-Value Hardening Backlog

1. Add strict transaction-boundary policy for CRUD composition.
2. Introduce migration tooling with explicit revisions and up/down semantics.
3. Add sequence reconciliation step to migration script.
4. Add pre-restore backup validation beyond size checks.
5. Encode DB credentials safely when constructing DATABASE_URL.
6. Consider selective pooling strategy for production throughput.
 7. Add stricter DB-level constraints for any future audit/event tables if persistent observability is reintroduced.

## Bottom Line

The database layer is clear and maintainable for a compact service, and startup sequencing is materially improved by DB readiness gating. The most important remaining gaps are not table-count complexity but operational rigor: transaction atomicity discipline, migration determinism, and restore safety guarantees under failure conditions.
