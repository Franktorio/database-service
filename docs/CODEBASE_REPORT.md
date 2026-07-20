# Full Codebase Report

## Scope

This report is a static engineering review of the repository as it exists on 2026-07-20. It covers the bootstrap path, configuration, API surface, authentication, authorization, JWT/cookie handling, rate limiting, IP blocking, database schema, CRUD behavior, background services, migration/setup scripts, logging, and deployment assumptions.

It does not claim production benchmarking or runtime proof. The environment available during this pass did not have the Python dependencies installed, so the review is based on source inspection plus targeted syntax validation.

## Executive Summary

This is a functional small-service control plane with a coherent structure and a relatively understandable code path. It is good enough for a personal tool, a low-traffic internal admin service, or an early prototype. It is not yet at the reliability, consistency, or operational maturity level expected of an industry-standard production authentication/admin service.

The strongest aspects are:

- Clear separation of API, CRUD, models, security, and service modules.
- Hashed storage for API keys and cookie token identifiers.
- Non-development secret safety enforcement.
- Simple optional-session pattern for most system CRUD helpers.

The weakest aspects are:

- Control-plane behavior is tightly coupled to synchronous persistent logging.
- Ratelimit and IP-block state is process-local and inconsistent across scaling boundaries.
- Several auth and operations behaviors are internally inconsistent or dangerously optimistic.
- Database lifecycle management is still closer to a bootstrap utility than a mature migration/HA story.

## What Is Strong

### Code Organization

The repository is laid out in a way that a new engineer can follow:

- `src/api` owns HTTP registration.
- `src/models` owns persistence.
- `src/security` owns auth and throttling primitives.
- `src/services` owns background behavior.

That is materially better than many small internal tools, which often collapse all of this into one or two files.

### Secret Handling Baseline

The configuration loader refuses default secrets in non-development mode for the database password, API-key pepper, password pepper, and JWT secret. That is a solid baseline control and above average for hobby-grade services.

### Secret Storage Model

Raw API keys are not stored in the database. Cookie tokens are also stored as hashes rather than plaintext values. That is the right default direction and aligns with normal industry expectations.

### Basic Auditability

Persistent logging of auth, rate-limit, and IP-block events gives the codebase some operational traceability. The logs are not structured enough for a mature observability stack, but they are still more useful than no persistent audit trail.

## What Is Weak

### Authentication Consistency

The cookie auth flow mixes multiple sources of truth:

- Login sets one cookie policy.
- Refresh sets another cookie policy.
- Cookie naming is split between a constant and an environment variable.

That kind of inconsistency is exactly how real production auth bugs happen.

### Authorization Freshness

API-key authorization is cached in memory. Once a key is cached, later DB deletes, permission downgrades, or rate-limit changes are not immediately enforced. This makes the system operationally surprising and undermines the admin API’s authority.

### Scalability Model

The stateful control-plane protections are entirely in memory:

- API-key ratelimits
- cookie ratelimits
- password-login ratelimits
- IP blocking

That means behavior is per-process, reset on restart, and not shared across instances. This is acceptable for a one-process service and weak by industry standards.

### Database Ops Maturity

The service does not use a migration framework such as Alembic. Instead it uses metadata creation plus a compatibility copy/swap script. That is workable early on, but it is fragile once the schema starts evolving under real data retention requirements.

### Runtime Efficiency

The engine uses `NullPool`, SQL echo is forced on, and several hot auth paths do DB writes for log events. Those choices are acceptable in development and harmful as traffic or operational pressure rises.

## What Is Likely To Fail

### 1. Cookie Rate Limiting Will Not Behave As Intended

Likely failure:

- The cookie limiter key is the current token hash.
- Successful requests rotate the JWT and its hash.
- The next request is effectively using a new limiter identity.

Result:

- Cookie rate limiting is largely bypassed by the normal success path.

Why this matters:

- This defeats one of the core protections on authenticated browser traffic.

### 2. API-Key Revocation and Permission Changes Can Lag

Likely failure:

- An API key is cached.
- The DB row is deleted or downgraded.
- The in-memory limiter entry continues authorizing until it expires from cache.

Result:

- Revoked credentials can continue to function temporarily.

Why this matters:

- That is below normal expectations for admin credential management.

### 3. Healthcheck Can Cause Self-Inflicted Recovery

Likely failure:

- `pg_isready` returns an auth-related failure because no password is supplied.
- The service interprets that as DB unhealthiness.
- Auto-restore or shutdown logic triggers.

Result:

- A healthy database can be treated as broken.

Why this matters:

- Automated recovery is more dangerous than helpful if liveness signals are noisy.

### 4. Cookie Login May Break Across Environments

Likely failure:

- Initial login writes a non-secure Strict cookie under one naming path.
- Subsequent authenticated responses refresh using a secure Lax cookie under another configuration path.

Result:

- Environment-specific auth drift, especially behind TLS termination or during local testing.

Why this matters:

- Auth bugs that only appear after deployment are costly and hard to debug.

### 5. Migration Can Succeed Then Fail on the Next Insert

Likely failure:

- Rows are copied into a fresh database with explicit IDs.
- Backing sequences are not reset.

Result:

- Later inserts can collide with already-used IDs.

Why this matters:

- That is a classic latent migration bug.

### 6. Healthcheck Restore Can Compound Damage

Likely failure:

- A dump is replayed into the current database rather than restored into a clean replacement target.

Result:

- Duplicated rows, partially overlapped state, or mixed old/new data.

Why this matters:

- Recovery code must be safer than the failure it is responding to.

### 7. Startup Order Can Trigger Early Thread Errors

Likely failure:

- Background services start before schema initialization completes.
- A service hits a table that does not exist yet.

Result:

- Cold boot races, early errors, or silently degraded background behavior.

Why this matters:

- Production startup must be deterministic.

## Nitpicky Findings By Area

### Bootstrap and Lifecycle

- Background daemon threads are started before DB schema initialization.
- If `API_ENABLED` is false, the process effectively exits after starting daemon threads, which then die with the main thread.
- Logging initialization happens before some imported modules may emit config warnings, so very early logs may not consistently land in the final sinks.

### Configuration

- DB credentials are interpolated directly into the connection URL without URL-encoding.
- The config model is environment-variable based but still relies on several hardcoded defaults that are safe only by convention.
- Some auth-relevant settings are split between config values and hardcoded constants.

### API Design

- Admin `GET` endpoints take `api_key` as a query parameter, which is not ideal for secret hygiene.
- The root endpoint is IP-block protected, which makes it a weak health/liveness probe.
- Route naming is serviceable but still biased toward CRUD verbs rather than resource-first design.

### Authentication and Authorization

- API-key revocation is not strongly immediate.
- Cookie refresh mutates session identity on every successful request.
- Role storage is flexible but enforced through app logic instead of stronger relational constraints.
- Password auth persistence and logging happen inline on the request path.

### Rate Limiting and Abuse Controls

- All ratelimits are local-memory only.
- Rate limits accept invalid values through request models.
- Proxy awareness is absent for IP-based controls.
- Restarting the process clears enforcement state.

### Database Schema and CRUD

- The recent index additions improve the hottest cleanup/retrieval paths.
- The schema still lacks foreign-key enforcement between `auth_cookies.username` and `users.username`.
- Some multi-step user update flows commit auth-cookie deletion before the broader operation finishes.

### Background Services

- Backup is straightforward but writes unencrypted SQL dumps locally.
- Healthcheck recovery is too aggressive for the quality of the health signal.
- Cookie-expiry cleanup uses `asyncio.run()` inside a loop in a thread, which works but is not especially elegant or resilient.

### Migration and Setup Scripts

- `setup_postgres.py` assumes Debian/Ubuntu, `apt`, `systemd`, `sudo`, and operator privilege model alignment.
- The README deployment flow can imply easier automation than the script really supports.
- `generate_api_key.py` is a bootstrap dependency but may fail on a pristine DB if schema is not initialized first.

### Logging and Observability

- Logs are human-readable but not structured for serious analysis.
- SQL echo in non-development environments is noisy and can leak operational details.
- Persistent logging on hot auth paths creates avoidable coupling between auditability and availability.

## Capacity Estimate

This codebase is not ready for a precise user-capacity number because the real limit depends heavily on:

- CPU count
- PostgreSQL latency
- disk speed for logs and dumps
- number of workers
- auth mix
- failure-path frequency

Still, a reasonable engineering estimate is possible.

Assumptions:

- One Uvicorn worker.
- Same-host or same-LAN PostgreSQL.
- 2 to 4 vCPU.
- Default logging behavior still enabled.
- No Redis, no shared cache, no queue, no external session store.

Estimated handling:

- Around 100 to 250 requests/second for simple API-key-protected admin reads in favorable conditions.
- More like 30 to 80 requests/second for cookie-authenticated flows, because those requests perform several DB lookups/writes and rotate session state.
- Roughly tens to low hundreds of concurrently active human users, not thousands, before operational rough edges become the dominant risk.

If you mean named users in the database rather than simultaneously active users, the schema itself could store far more than that. The limiting factor is request-path design, not row count.

## Comparison To Industry Standards

### Where It Meets Basic Expectations

- Secret hashing for stored credentials.
- Separation of concerns in code layout.
- Use of parameterized SQLAlchemy queries rather than raw SQL for the main app.
- Basic audit logging and backup support.

### Where It Falls Short

- No formal migration system.
- No shared/distributed rate limiting.
- No clear transactional boundaries for some multi-step auth-related updates.
- No proxy-aware client-IP handling.
- Inconsistent cookie security behavior.
- Overly coupled auth and persistent logging paths.
- Operational recovery logic that is too optimistic for production use.
- No evidence here of test coverage, CI quality gates, metrics, tracing, or structured health endpoints.

Compared to a mature industry-standard admin/auth service, this is several steps behind in correctness, observability, and operational safety.

Compared to a typical personal/internal prototype, it is above average in structure and below average in production-hardening.

## Recommended Priority Order

1. Fix cookie-rate-limit identity and API-key cache invalidation semantics.
2. Unify cookie configuration and remove hardcoded naming/TTL mismatches.
3. Repair healthcheck signaling and disable destructive restore behavior until recovery is safe.
4. Add request-model validation for rate limits, permission levels, and other critical fields.
5. Move toward proper migrations and stronger DB integrity constraints.
6. Replace process-local abuse-control state with a shared store if multi-instance deployment is a goal.
7. Reduce hot-path DB logging pressure and improve observability with structured logs/metrics.

## Changes Made During This Pass

This review pass also added explicit index declarations for active system-table access patterns:

- `api_keys.created_at`
- `auth_cookies.username`
- `auth_cookies(expires_at, revoked)`
- `persistent_logs.created_at`

`src/models/database.py` now also ensures declared indexes are created on startup with `checkfirst=True`, which helps existing databases converge to the current model metadata without requiring a full migration just for these indexes.
