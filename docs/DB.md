# Database Reference

The database layer is still small, but it is no longer limited to API keys. The live schema contains four system tables and several operational assumptions that matter for performance and maintenance.

## Schema Initialization

`src/models/database.py` initializes schema directly from SQLAlchemy metadata during API startup.

Current startup behavior:

- Creates any missing tables with `Base.metadata.create_all`.
- Creates any declared SQLAlchemy indexes with `checkfirst=True` so existing databases can pick up missing indexes without a full rebuild.
- Uses an async SQLAlchemy engine with `NullPool`.
- Keeps `echo=True` enabled in the engine.

## Current Tables

### `users`

Purpose:

- Stores login identities and password-hash metadata.
- Stores role membership and per-user login rate limit.

Key columns:

- `id` primary key
- `username` unique
- `password_hash`
- `password_salt`
- `hash_iterations`
- `hash_algorithm`
- `email`
- `roles` as `ARRAY(String)`
- `login_rate_limit`
- `created_at`
- `last_updated_at`

Index coverage:

- Unique constraint on `username` provides the critical lookup index.

### `api_keys`

Purpose:

- Stores hashed API keys plus permission and rate-limit settings.

Key columns:

- `id` primary key
- `key_hash` unique
- `permission_level`
- `rate_limit`
- `email`
- `created_at`
- `last_updated_at`

Index coverage:

- Unique constraint on `key_hash`.
- Explicit index on `created_at` to support ordered listing.

### `auth_cookies`

Purpose:

- Stores hashed cookie JWT identifiers for revocation and expiry checks.

Key columns:

- `id` primary key
- `token_hash` unique
- `username`
- `expires_at`
- `revoked`
- `created_at`

Index coverage:

- Unique constraint on `token_hash`.
- Explicit index on `username` for user-scoped session invalidation.
- Explicit composite index on `(expires_at, revoked)` for expiry sweeps.

Notes:

- `username` is not a foreign key to `users`; integrity is enforced in application code only.

### `persistent_logs`

Purpose:

- Stores auth, rate-limit, and IP-block events for persistent audit visibility.

Key columns:

- `id` primary key
- `log_type`
- `log_level`
- `message`
- `ip_address`
- `created_at`

Index coverage:

- Explicit index on `created_at` for recent-log retrieval and age-based deletion.

## CRUD Conventions

System CRUD modules generally follow this pattern:

- Accept optional `session: AsyncSession | None = None`.
- If no session is passed, open `SessionLocal()` internally.
- Track whether the function owns the session and close it only in that case.

That pattern is useful for composition, but some multi-step flows still commit intermediate side effects before the broader logical operation is finished.

## Migration Behavior

`scripts/migrate_db.py` creates a temporary database from current metadata, copies rows from common tables using exact column/type matches, then swaps database names.

Important caveats:

- Renamed or type-changed columns are skipped rather than failing hard.
- Sequence reset behavior is not currently documented or enforced after explicit ID copy.
- This script is better described as a compatibility copy-and-swap than a full migration framework.

## Operational Notes

- The service is currently single-node oriented.
- In-memory auth/ratelimit state is not stored in PostgreSQL.
- Persistent logs add write traffic on authentication code paths.
- Backups are plain SQL dumps written to local disk.
