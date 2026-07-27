# Engineering Report — Clean Database Service

**Prepared:** 2026-07-27
**Scope:** Full repository audit (`config/`, `main.py`, `src/`, `migrations/`, `tools/`)
**Method:** Manual line-by-line review of every module, cross-referenced against OWASP ASVS/Top 10, REST/HTTP conventions, and common production-backend practice for small async Python services.
**Context acknowledged:** This is a development-stage codebase. There are no real clients, no production data, and only a single fresh Alembic migration. Findings are scored against *industry practice for code destined for production*, not against "is this OK for a hobby project" — but the roadmap at the end is sequenced with the pre-production status in mind.

> This report is intentionally direct. Scores reflect where the code would land in a professional code review / architecture review, not effort or intent.

---

## Executive Summary

| # | Category | Score /10 | One-line verdict |
|---|---|:---:|---|
| 1 | Project Architecture | **7.0** | Clean layering, but the "system vs. app" boundary is a convention, not an enforced one |
| 2 | Code Quality | **6.5** | Readable and consistent naming, but real duplication and 3 competing versions of the same pattern |
| 3 | Database Design | **6.5** | Correct FKs/indexes/timestamps, but a denormalized cookie table and unbounded list queries |
| 4 | API Design | **6.0** | Sensible REST resource shape, but auth is invisible to OpenAPI and error shapes are inconsistent |
| 5 | Security | **7.5** | Genuinely above-average secret hygiene and fail-closed design; missing CSRF/MFA/audit trail |
| 6 | Reliability | **7.0** | Solid supervised background tasks; the auto-restore recovery path is a loaded gun |
| 7 | Performance | **5.5** | Good async DB pooling undone by a **blocking CPU-bound call inside the event loop** |
| 8 | Testing | **2.5** | One live smoke-test script; zero unit tests, zero CI, zero mocking |
| 9 | Production Readiness | **5.0** | Strong config/secrets discipline; no containerization, monitoring, or off-box backups |
| 10 | Professional Engineering Standards | **6.5** | Mid-level work with senior-level instincts in security; testing/ops maturity lags behind |

**Overall: ~6.2 / 10 — a competent, security-conscious mid-level codebase that is not yet production-ready**, primarily due to testing gaps, a blocking-call concurrency bug, and missing operational tooling (containers, monitoring, off-box backups).

> **Resolved since initial audit (2026-07-27, same day):** Seven findings below have already been fixed and are annotated inline where they appear (✅): (1) the five independent `json.loads(service_config.json)` call sites and the three divergent `cache_invalidating` decorator implementations were both consolidated — see [`config/settings.py`](../config/settings.py) and [`src/models/crud/cache_invalidation.py`](../src/models/crud/cache_invalidation.py); (2) the dead `ratelimit_cache`/`ip_block_cache` config sections were removed from `config/service_config.json`; (3) **the blocking PBKDF2 call — originally called out as the single most significant finding in this report — is fixed**: `verify_password()` (`src/security/tokens.py`) now offloads its PBKDF2 computation via `asyncio.to_thread`, verified under a concurrency test to no longer stall the event loop; (4) cookie authentication is now cached in Redis (`_resolve_cookie_row()` in `src/security/validation/cookie_security.py`), closing the caching asymmetry with the API-key path; (5) **the `@api_authentication`/`@cookie_authentication` decorator stacks have been replaced with FastAPI `Depends()`-based dependency chains** — `api_key_authorized_factory()`/`api_key_rate_limited_factory()`/`get_current_api_key()` in [`src/security/validation/api_security.py`](../src/security/validation/api_security.py), and `cookie_authorized_factory()`/`get_current_cookie_data()`/`cookie_rate_limited_factory()`/`get_cookie_claims()` in [`src/security/validation/cookie_security.py`](../src/security/validation/cookie_security.py). Every `system` route now declares its auth requirement as a typed parameter (`Depends(...)`) instead of a bare decorator, so it is visible in the OpenAPI schema. `with_ip_block` intentionally remains a decorator (it is unconditional, IP-only, and has no FastAPI-visible request/response contract worth exposing as a dependency); (6) **the inconsistent error envelope is fixed**: every raised `HTTPException` across the codebase now goes through [`api_error()`](../src/api/errors.py), which always produces `detail: {"error": "...", "retry_after": <seconds-or-null>}` — there is exactly one shape for `response.json()["detail"]` now, not two; (7) **every route now declares `response_model=`**: typed response models (e.g. `ApiKeyListResponse`, `UserCreateResponse`) were added to each endpoint folder's `models.py` ([`api_db_endpoints/models.py`](../src/api/system/api_db_endpoints/models.py), [`user_db_endpoints/models.py`](../src/api/system/user_db_endpoints/models.py)) and wired onto every route, so response shapes are validated by Pydantic and documented in the OpenAPI schema instead of being hand-built untyped dicts. The category scores above reflect the original audit and have **not** been recalculated — treat them as a snapshot as of the date above, not a live number. The [Concurrent User Capacity Estimates](#concurrent-user-capacity-estimates--10-vps-single-node) section below **has** been revised, since its numbers were explicitly built around the now-fixed PBKDF2 bottleneck.

---

## 1. Project Architecture

**Score: 7.0 / 10**

#### What's done well

- Clear **layered separation**: `api/` (HTTP concerns) → `security/` (auth/crypto) → `models/crud` (data access) → `models/tables` (schema). Nothing in `models/tables` imports upward, and route handlers never touch SQLAlchemy directly — they always go through a CRUD function.
- The `src/services/system/cache` package cleanly isolates Redis concerns (client, rate limiting, permission caching, Lua scripts) behind small async functions, so callers never see the Redis driver directly.
- Background work (`backup.py`, `dbhealthcheck.py`, `cookieexpiry.py`) is decoupled from the request path and centrally supervised by [`TaskSupervisor`](../src/services/supervisor.py), a genuinely nice piece of infrastructure: restart-with-backoff for free, applied uniformly to every long-running loop.
- `config/loader.py` is a single, well-documented source of truth for environment configuration, with a startup-time safety gate (`_enforce_secret_safety`) — a pattern many production systems lack even at maturity.

#### What's below industry standard

- The intended **"system" vs. "application" boundary is purely a folder-naming convention** (`src/api/system/...`, `src/services/system/...`). Nothing prevents a future feature from importing internals of the system layer, and there is no `__all__`, package-private prefix, or architectural test (e.g., `import-linter`) enforcing it. The user's own request to "expand outside of `/system`" is evidence this boundary matters, yet it is unguarded.
- **✅ Resolved.** This originally described cross-cutting concerns wired by hand in every route file, with every route repeating `@with_ip_block` then `@api_authentication(permission_level=...)`/`@cookie_authentication(...)` and nothing to catch a forgotten or misordered decorator. Auth is now composed via FastAPI `Depends()` chains (`api_key_authorized_factory(...)` / `cookie_authorized_factory(...)` in `src/security/validation/`), declared as typed parameters on every route in `src/api/system/*/routes/_*.py`. `with_ip_block` remains a decorator by design (see the note at the top of this report) but is still applied uniformly.
- **✅ Resolved.** This originally described configuration split across `.env` (`config/loader.py`), ad hoc `json.loads(Path(...).read_text())` reads of `config/service_config.json` duplicated across `backup.py`, `dbhealthcheck.py`, `cookieexpiry.py`, `setup_postgres.py`, and `setup_redis.py`, and in-code constants (`src/api/config.py`). [`config/settings.py`](../config/settings.py) now parses `service_config.json` exactly once into typed, validated Pydantic models (`BackupSettings`, `DbHealthCheckerSettings`, `SetupPostgresSettings`, `SetupRedisSettings`, `CookieExpirySettings`, `RedisIndexPrefixes`), eliminating the five duplicated call sites. **What remains:** `.env` (`config/loader.py`) and `service_config.json` (`config/settings.py`) are still two separate loading mechanisms rather than one unified `Settings` object, and the new models use Pydantic's default "ignore unknown fields" behavior, so a stray or typo'd top-level key would still be silently ignored rather than raising at startup.

#### What a senior engineer would likely change

- **✅ Done for `service_config.json`:** [`config/settings.py`](../config/settings.py) now validates it once via typed Pydantic models. **Still open:** merge this with `.env` loading (`config/loader.py`) into one unified `Settings` object (e.g. via `pydantic-settings`), and consider `model_config = {"extra": "forbid"}` on the section models so an unrecognized key fails fast instead of being silently ignored.
- **✅ Done:** repeated `@with_ip_block` + `@api_authentication(...)`/`@cookie_authentication(...)` decorator stacks have been replaced with FastAPI `Depends()`-based security dependencies, so route wiring is declarative and appears in OpenAPI.
- Add a lightweight import-boundary check (even a simple grep-based CI step, or `import-linter`) so "no application code imports from `system` internals" is enforced, not just documented.

#### Severity

**Medium.** None of this blocks correctness today, but every one of these issues compounds as the codebase grows — the exact moment the user plans to add non-system features.

---

## 2. Code Quality

**Score: 6.5 / 10**

#### What's done well

- Naming is consistent and descriptive throughout (`add_user`, `get_user_by_username`, `update_user_login_rate_limit` — CRUD names read like sentences).
- A consistent `PRINT_PREFIX` + [`log_message`](../src/services/system/logging.py) convention makes log lines greppable across the whole codebase.
- Pydantic models are used correctly for request validation everywhere (`ApiKeyCreateRequest`, `UserUpdateRequest`, etc.), with `Field(..., ge=..., le=...)` constraints doing real validation work instead of manual `if` checks.
- Type hints (`str | None`, `list[str]`, `AsyncSession | None`) are used consistently across nearly every function signature.

#### What's below industry standard

- **✅ Resolved.** This originally described the same "invalidate cache after write" concept being implemented three different ways across `user_crud.py` (a plain decorator), `api_key_crud.py` (an independently duplicated copy of that decorator), and `auth_cookie_crud.py` (a differently-shaped decorator factory) — three files, one concept, three implementations, two different APIs sharing one function name. [`src/models/crud/cache_invalidation.py`](../src/models/crud/cache_invalidation.py) now provides the single shared `cache_invalidating(invalidator)` decorator factory plus identifier-builder helpers (`user_identifier`, `api_key_identifier`, `cookie_identifier`, `password_identifier`, `ip_block_identifier`), and all three CRUD modules — plus `src/security/ip_block.py`, `api_security.py`, `cookie_security.py`, and `password_security.py` on the read/enforcement side — now import from it instead of re-deriving their own Redis key prefixes.
- CRUD read functions (`get_users`, `get_api_keys`, `get_user_by_username`, `get_api_key`, …) are near-identical boilerplate (select → execute → scalar(s)) repeated 8+ times with no shared generic helper. *(Still open.)*
- No linter, formatter, or static type checker is configured anywhere in the repository (no `ruff`/`flake8`/`black`/`mypy` config; the only mentions of `black`/`ruff` are commented-out boilerplate in `alembic.ini`). Style consistency today relies entirely on manual discipline. *(Still open.)*
- **✅ Resolved.** `config/service_config.json` no longer defines the dead `ratelimit_cache`/`ip_block_cache` blocks this finding originally flagged as unread leftover configuration.

#### What a senior engineer would likely change

- **✅ Done:** the three cache-invalidation decorators have been collapsed into one shared utility, [`src/models/crud/cache_invalidation.py`](../src/models/crud/cache_invalidation.py), with a single call signature.
- Extract a small generic `get_by_field(model, field, value, session)` / `list_all(model, order_by, session)` helper to remove repeated boilerplate. *(Still open.)*
- Add `ruff` (lint + format) and `mypy` to `requirements.txt` / a `pyproject.toml`, wired into CI. *(Still open.)*
- **✅ Done:** the dead `ratelimit_cache`/`ip_block_cache` config sections have been removed from `config/service_config.json`.

#### Severity

**Low-to-Medium.** Nothing here is a bug, but the duplicated decorator pattern was exactly the kind of thing that would have caused a real bug the next time someone modified one copy and forgot the other two — that specific risk is now mitigated by the consolidation into `cache_invalidation.py`. The remaining CRUD-boilerplate duplication and missing lint/type tooling keep this category's residual severity at Low-to-Medium.

---

## 3. Database Design

**Score: 6.5 / 10**

#### What's done well

- Proper use of SQLAlchemy 2.0 **typed `Mapped`/`mapped_column`** declarative style throughout — this is the current idiomatic SQLAlchemy API, not the older `Column()` style.
- Correct **foreign keys with `ondelete="CASCADE"`** from `auth_cookies` to `users` (both `username` and `user_id`), so deleting a user cannot orphan cookie rows.
- Sensible indexing: `ix_auth_cookies_expires_at_revoked` composite index directly supports the cookie-expiry sweep query; `created_at` is indexed on `api_keys` for chronological listing.
- Timestamps use `server_default=func.now()` (DB-generated, not app-generated) for `created_at`/`last_updated_at`, which is the correct approach — it survives bulk inserts and clock skew between app instances.
- `Base` (in [`src/models/base.py`](../src/models/base.py)) uses `MappedAsDataclass`, giving every model a clean `__init__` and `to_dict()`/`from_dict()` for free — a nice, lightweight convention.

#### What's below industry standard

- `AuthCookie` stores **both** `username` and `user_id` as separate foreign keys to `users` — a denormalization that exists purely for query convenience. It works today because both are cascade-deleted together, but it is two sources of truth for "which user" and would need careful handling the moment usernames become mutable.
- `roles: Mapped[list[str]] = mapped_column(ARRAY(String), ...)` stores roles as a Postgres array instead of a normalized `roles`/`user_roles` join table. This is a pragmatic shortcut, not schema design — it works for a handful of roles but cannot express role metadata (descriptions, permission sets, hierarchies) or be queried efficiently at scale (`WHERE 'admin' = ANY(roles)` doesn't use a standard B-tree index well without a GIN index, which isn't defined).
- **No pagination anywhere.** `get_users()` and `get_api_keys()` (and their routes) fetch and serialize the *entire* table on every call. Fine at 50 rows, a real problem at 50,000.
- Only one Alembic revision exists (expected, given the dev-only status), but there is no evidence the `downgrade()` path has ever been exercised — a common gap that turns into a production incident the first time a rollback is actually needed.
- No soft-delete/audit columns (`deleted_at`, `updated_by`) on any table — deletions are hard `DELETE` statements with no forensic trail (see `delete_user`, `delete_api_key`).

#### What a senior engineer would likely change

- Add a `GIN` index on `roles` if array-membership queries are expected to stay in production, or migrate to a normalized `roles`/`user_roles` table once role metadata is needed.
- Add `LIMIT`/`OFFSET` (or keyset pagination) to every list endpoint before the tables can grow unbounded.
- Exercise/test the `downgrade()` migration path at least once, and add a CI step that runs `alembic upgrade head && alembic downgrade base` against a throwaway database.
- Consider whether `username` on `auth_cookies` is needed at all, given `user_id` already identifies the row uniquely (a join gets the username when needed).

#### Severity

**Medium.** None of this causes incorrect behavior today at low volume; all of it becomes a real cost as row counts grow, which is exactly why it should be addressed before real users arrive.

---

## 4. API Design

**Score: 6.0 / 10**

#### What's done well

- Route structure is properly resource-oriented and RESTful: `GET/POST /api/db/keys`, `PATCH/DELETE /api/db/keys/{key_id}`, `GET/POST /api/db/users`, `PATCH/DELETE /api/db/users/{username}`, plus sub-resources like `PATCH /api/db/users/{username}/password` and `.../login-rate-limit`. This is a clean, conventional REST shape (git history confirms this was deliberately migrated *from* an RPC-style API — a good decision).
- Correct status codes are used where it counts: `404` for missing resources, `409` for duplicate user creation, `429` for rate limiting, `503` for upstream (Redis) unavailability.
- Request validation is delegated entirely to Pydantic models with real constraints (`ge=VIEW_LEVEL, le=SUPER_ADMIN_LEVEL`), so malformed input is rejected before handler code runs.
- A deliberate, sound security decision: `POST /api/db/keys` and `PATCH /api/db/keys/{key_id}` explicitly **refuse** to create/promote a key to `SUPER_ADMIN_LEVEL` over the API — that privilege escalation path is closed off by design, forcing bootstrap via `tools/scripts/generate_api_key.py` on the host.

#### What's below industry standard

- **✅ Resolved.** Because auth was previously enforced via bare `@api_authentication(...)`/`@cookie_authentication(...)` decorators instead of a FastAPI `Security`/`Depends()` dependency, the auto-generated `/docs` Swagger UI showed these endpoints as if they took no credentials at all. Auth is now expressed as `Depends(api_key_authorized_factory(...))` / `Depends(cookie_authorized_factory(...))` parameters on every route, so the generated OpenAPI schema reflects the real credential requirement per route.
- **✅ Resolved.** This originally described the public resource identifier for API keys being the internal `key_hash` (a SHA-256 digest) leaking out via `to_dict()`, rather than a deliberate opaque `id`. `key_hash` is no longer part of any response model (see [`ApiKeyItem`](../src/api/system/api_db_endpoints/models.py)) — `GET/POST /api/db/keys` return the row's numeric `id` instead, and `PATCH`/`DELETE /api/db/keys/{key_id}` now look the row up by that `id` (`update_api_key_by_id`/`delete_api_key_by_id` in [`api_key_crud.py`](../src/models/crud/system/api_key_crud.py)). `key_hash` remains purely an internal Postgres/Redis lookup value.
- **✅ Resolved.** This originally described most `HTTPException`s using a plain string `detail` while rate-limit/IP-block paths used a `dict`. Every raised exception now goes through [`api_error()`](../src/api/errors.py) (`src/api/errors.py`), which always builds `detail: {"error": "...", "retry_after": <seconds-or-null>}` — a single client-side error handler can now rely on one shape for `response.json()["detail"]` everywhere.
- No API versioning scheme (`/v1/...`) — any breaking change to these contracts has no migration path for existing consumers.
- **✅ Resolved.** Every route in `src/api/system/*/routes/_*.py` now declares `response_model=` (see each endpoint folder's `models.py`), so FastAPI validates and documents response shapes; a typo'd or missing key in a hand-built dict would now surface as a `ResponseValidationError` instead of silently reaching the client.

#### What a senior engineer would likely change

- **✅ Done:** auth now flows through FastAPI dependencies (`Depends(api_key_authorized_factory(SUPER_ADMIN_LEVEL))` / `Depends(cookie_authorized_factory(...))`) so `/docs` reflects reality and 401/403/429/503 responses are visible on the declared route parameters.
- **✅ Done:** all error responses now use a single envelope via `api_error()` (`{"detail": {"error": "...", "retry_after": ...}}`).
- **✅ Done:** every route now declares `response_model=` for response validation and accurate OpenAPI output.
- Introduce `/v1` prefix now, while there are zero real consumers, rather than after the first breaking change is needed.

#### Severity

**Medium.** The API works and is reasonably conventional, but a new integrator relying on `/docs` alone would be actively misled about auth requirements — that's a real, user-facing gap, not a cosmetic one.

---

## 5. Security

**Score: 7.5 / 10**

This is the strongest category in the codebase, and it shows deliberate security awareness rather than default-happy-path coding.

#### What's done well

- **Fail-closed startup validation.** [`config/loader.py`](../src/api/../../config/loader.py)`._enforce_secret_safety()` raises `RuntimeError` and refuses to boot in any non-development mode if `POSTGRESQL_PASSWORD`, `API_KEY_PEPPER`, `PASSWORD_PEPPER`, `JWT_SECRET`, or `REDIS_PASSWORD` are left at documented default/placeholder values. Many production systems never get this far.
- **Peppered, salted, iterated password hashing**: PBKDF2-HMAC-SHA256 with a per-user random salt (`generate_password_salt`), a global pepper (`PASSWORD_PEPPER`), and a configurable iteration count (210,000 by default) stored per-user (`hash_iterations`) so it can be upgraded without breaking old hashes. Constant-time comparison via `hmac.compare_digest` in `verify_password` correctly avoids timing attacks.
- **API keys and JWTs are never stored raw.** Only `sha256(pepper:token)` hashes live in Postgres (`key_hash`, `token_hash`); logs consistently truncate to a fingerprint (`token_hash[:12]`) rather than logging secrets.
- **Hybrid JWT design**: cookie sessions are signed JWTs (stateless, fast to verify) *plus* a server-side `auth_cookies` row that allows real revocation (`revoke_auth_cookie`, `revoke_expired_auth_cookies`) — solving the classic "JWTs can't be revoked" problem without going fully stateful.
- **Layered abuse defense**: per-identity Redis rate limiting (API key, cookie, and username-based login attempts) *and* a separate IP-burst blocker (`with_ip_block`), and both **fail closed** — if Redis is unreachable, requests get `503`, not silently unlimited access. This is a materially better default than most side-project auth code.
- Cookies are `httponly`, `samesite=lax`, and `secure` is correctly tied to `OPERATING_MODE == "production"` rather than hardcoded.
- Privilege escalation to `SUPER_ADMIN` is explicitly blocked from the HTTP API (see API Design above) — a genuinely good defense-in-depth decision.

#### What's below industry standard

- **PBKDF2 instead of Argon2id.** Current OWASP password-storage guidance recommends Argon2id first, with PBKDF2 as an acceptable fallback only when Argon2 isn't available. 210,000 iterations of PBKDF2-SHA256 is reasonable but not best-in-class. *(The related availability issue — this hash running synchronously on the event loop, effectively a self-inflicted DoS vector — has since been fixed; see §7.)*
- **No CSRF protection** on cookie-authenticated state-changing requests. Today only the `/cookie-auth-test` route uses the cookie auth dependency chain (`cookie_authorized_factory()` in `src/security/validation/cookie_security.py`), so real-world exposure is currently zero — but the mechanism doesn't exist yet, and it is exactly the kind of control that's easy to forget once real cookie-authenticated mutation endpoints are added.
- **No persisted audit trail for admin actions.** Creating/deleting a user or API key is logged as a text line (`log_message`) but not written to a queryable table — after log rotation (7-day `TimedRotatingFileHandler` backlog), there is no way to answer "who created this API key and when" for anything older than a week.
- **No MFA / IP allowlisting for `SUPER_ADMIN` keys.** A single leaked bearer token grants full control over user and API-key administration for the entire system, with no secondary factor.
- No automated dependency vulnerability scanning (no `pip-audit`/`safety`/Dependabot configuration) despite depending on security-critical packages (`PyJWT`, `asyncpg`, `redis`).

#### What a senior engineer would likely change

- **✅ Done:** `verify_password` now offloads its PBKDF2 computation to a thread via `asyncio.to_thread` (see §7). `hash_password` itself is still called synchronously from the (low-frequency, `SUPER_ADMIN`-only) user-creation and password-rotation routes — lower risk than the public login path, but the same offload is worth applying there too for consistency.
- Add a persisted `admin_audit_log` table (actor key fingerprint, action, target, timestamp, source IP) written on every mutating system-admin route.
- Add CSRF tokens (double-submit cookie or `SameSite=strict` + custom header check) before any real cookie-authenticated mutation route ships.
- Plan a migration path to Argon2id (`argon2-cffi`) using the existing `hash_algorithm`/`hash_iterations` per-user columns as a natural versioning mechanism — the schema already supports a gradual rollout.

#### Severity

**Medium** overall (the fundamentals are genuinely solid), but **High** specifically for the missing admin audit trail and MFA on `SUPER_ADMIN` keys, given how much power a single token grants.

---

## 6. Reliability

**Score: 7.0 / 10**

#### What's done well

- [`TaskSupervisor`](../src/services/supervisor.py) gives every background loop restart-with-exponential-backoff semantics uniformly, with a bounded attempt count (`DEFAULT_TASK_RESTART_ATTEMPTS`) so a persistently crashing task doesn't spin forever.
- The DB health checker (`src/services/system/dbhealthcheck.py`) is thoughtfully designed for a "no 24/7 human monitoring" deployment: configurable `leniency` before acting, a **mandatory pre-restore safety backup** (`create_pre_restore_backup`) before ever dropping the database, and bad backups are quarantined (`bad_backups/`) rather than deleted, preserving forensic evidence.
- Redis-dependent code paths fail closed (`503`) instead of failing open — correctly prioritizing safety over availability for security-relevant checks.
- Graceful shutdown in `app.py`'s `lifespan` cancels all background tasks, closes the Redis client, and disposes the DB engine in an explicit, ordered sequence.

#### What's below industry standard

- The auto-rollover recovery path is **destructive by nature**: `restore_from_backup()` calls `drop_database()` (terminating all connections and dropping the DB) before restoring. With the default `interval: 1800` (30 minutes) backup cadence, a triggered auto-rollover can **lose up to 30 minutes of writes** — acceptable as a documented last resort, but the code has no dry-run mode, no operator confirmation step, and (thankfully) ships with `auto_rollover: false` by default. If a future operator flips this on for a live system without understanding the tradeoff, this is a serious, silent data-loss trap.
- `shutdown_on_failure: true` calls `os.kill(os.getpid(), signal.SIGINT)` as the terminal fallback. This is a reasonable "fail loudly" choice, but **only if something outside the app restarts the process** — there is no systemd unit, Supervisor config, or Docker restart policy checked into the repository to guarantee that. As shipped, triggering this path is a full outage until a human intervenes.
- No circuit breaker or degraded-mode path exists for Redis: every single request (including the unauthenticated `/` root route, via `@with_ip_block`) depends on Redis being reachable. A Redis restart takes the *entire* API down even though Postgres may be perfectly healthy — see Architecture concern below.
- Logging (`src/services/system/logging.py`) uses an in-process `queue.Queue(maxsize=10000)` with a single worker thread; under sustained overload, `log_message` silently drops messages (`except queue.Full: pass`) rather than applying backpressure or alerting that logs are being lost — acceptable as a safety valve, but currently invisible (no counter/metric for dropped-log events).

#### What a senior engineer would likely change

- Ship a reference process-supervisor config (systemd unit or Docker `restart: always`) alongside `shutdown_on_failure`, since the feature is meaningless without one.
- Add a minimal in-process circuit breaker / short-lived local cache fallback for IP-block and rate-limit checks so a brief Redis blip degrades functionality (e.g., skip rate limiting for a few seconds) rather than taking the whole API offline.
- Expose a counter/metric for dropped log messages and queue depth so silent log loss under load is observable.
- Add an operator confirmation flag or dry-run mode to `auto_rollover` given its destructive blast radius.

#### Severity

**Medium**, trending toward **High** if `auto_rollover` is ever enabled without the operational safety net (process supervisor, alerting) being added alongside it.

---

## 7. Performance

**Score: 5.5 / 10**

#### What's done well

- The async SQLAlchemy engine is properly tuned, not left at defaults: `pool_size`, `max_overflow`, `pool_timeout`, `pool_recycle`, and `pool_pre_ping` are all environment-configurable (`config/loader.py` → `src/models/database.py`) — `pool_pre_ping` in particular is a detail many teams miss and then get bitten by stale-connection errors.
- API-key authorization is properly cached: `_get_api_permission_payload()` in [`api_security.py`](../src/security/validation/api_security.py) checks Redis first and only falls back to Postgres on a cache miss, keeping the hot authorization path off the database for repeat callers.
- Rate limiting and IP blocking are implemented as single **atomic Lua scripts** (`ratelimit_logic.lua`, `permissions_logic.lua`) executed via `EVAL`, avoiding read-modify-write race conditions that a naive GET-then-SET implementation would have under concurrent requests — this is a genuinely correct, non-trivial piece of engineering.

#### What's below industry standard

- **✅ Resolved — this was the most significant single finding in the original audit.** [`authenticate_password()`](../src/security/validation/password_security.py) is an `async def` that called `verify_password(...)` — a plain, synchronous, CPU-bound function performing 210,000 PBKDF2-SHA256 iterations (`src/security/tokens.py`) — without ever offloading it to a thread, fully blocking the single asyncio event loop for the duration of every login. [`verify_password()`](../src/security/tokens.py) now wraps its hash computation in `await asyncio.to_thread(_verify)`; verified with a concurrency test showing an unrelated `asyncio` task keeps making progress (50/50 scheduled ticks completed) while a full 210,000-iteration verification runs alongside it. **Residual, lower-severity gap:** `hash_password(...)` is still called synchronously (not offloaded) from the `SUPER_ADMIN`-only user-creation (`src/api/system/user_db_endpoints/routes/_post_routes.py`) and password-rotation (`_patch_routes.py`) routes — the same class of blocking call, but on a far lower-frequency, privileged-only path than the public login endpoint.
- **✅ Resolved.** Cookie authentication previously called `get_auth_cookie_by_hash(token_hash)` — a direct Postgres query — on every single cookie-authenticated request, unlike the API-key path (Redis-cached). [`_resolve_cookie_row()`](../src/security/validation/cookie_security.py) now checks Redis first via `cache_permission_json`/`get_cached_permission_json`, falling back to Postgres only on a cache miss, with invalidation wired through `invalidate_cookie_cache()` in [`cache_invalidation.py`](../src/models/crud/cache_invalidation.py) on every write path (add/revoke/refresh/expire).
- List endpoints (`GET /api/db/users`, `GET /api/db/keys`) have no pagination and load full result sets into memory and JSON-serialize them on every call (see Database Design). *(Still open.)*
- No response compression (no `GZipMiddleware`) and no HTTP caching headers (`ETag`/`Cache-Control`) on any read endpoint. *(Still open.)*

#### What a senior engineer would likely change

- **✅ Done:** `verify_password` is offloaded via `asyncio.to_thread`. Apply the same treatment to the remaining synchronous `hash_password(...)` call sites in the user-creation/password-rotation routes for full consistency.
- **✅ Done:** `auth_cookies` validity (`{revoked, expires_at, username, user_id}`) is now cached in Redis with invalidation on every write path, mirroring the API-key permission cache.
- Add pagination to both list endpoints before they're relied upon at scale. *(Still open.)*

#### Severity

**Was High** for the blocking PBKDF2 call on the login path — now resolved. **Low** residual severity remains for the still-synchronous `hash_password` calls on the (infrequent, privileged-only) user-creation/password-rotation routes. **Medium** for the remaining pagination/compression gaps.

---

## 8. Testing

**Score: 2.5 / 10**

#### What's done well

- [`tools/tests/live_system_api_test.py`](../tools/tests/live_system_api_test.py) is a genuinely thorough **end-to-end scenario** for what it covers: it exercises the full create → list → get → patch → rotate-password → old-cookie-rejected → new-cookie-accepted → rate-limit-429 → delete lifecycle for both users and API keys against a live server, and it cleans up after itself (deletes the user/key it created) using a timestamp nonce to avoid collisions.
- The rate-limit test (hammering `/api-auth-test` up to 100 times expecting a `429`) is a nice touch — it validates an actual runtime property, not just a status code.

#### What's below industry standard

- **There are zero unit tests.** Nothing in `security/tokens.py`, `security/validation/*`, `models/crud/*`, or `services/*` is tested in isolation. Every one of the concrete bugs identified in this report (the blocking PBKDF2 call, the missing cookie cache, the three divergent `cache_invalidating` implementations) has since been fixed by hand (see §2, §7) — but **none of those fixes are covered by an automated test**, so a future regression (someone re-introducing a synchronous `hash_password` call, or a fourth divergent cache-invalidation helper) would go undetected exactly as the originals did.
- The only test artifact **requires a fully running instance** (`SYSTEM_TEST_BASE_URL`) with a live Postgres, live Redis, and a manually bootstrapped `SYSTEM_TEST_SUPER_ADMIN_KEY` — it cannot run in a clean CI container without significant setup, and it is not wired into any CI pipeline (there is no `.github/workflows` or equivalent in the repository at all).
- No mocking/fixture layer exists for the database or Redis, so there is no way to test error paths (e.g., "Redis is down mid-request" → `503`) deterministically — those paths are currently unverified by any automated check.
- No coverage tooling (`coverage.py`/`pytest-cov`) and no way to answer "what % of this codebase is exercised by any test."
- Nothing tests the Alembic `downgrade()` path, the backup/restore cycle, or the health-check auto-rollover logic — arguably the highest-risk code in the entire repository (it can drop and restore the production database) has **no automated test coverage whatsoever**.

#### What a senior engineer would likely change

- Introduce `pytest` + `pytest-asyncio` immediately, with a fixture that spins up a disposable Postgres schema (e.g., via `testcontainers` or a dedicated test database) and a fake/real Redis instance for CI.
- Unit-test the security layer first: password hashing round-trips, JWT creation/expiry/invalid-signature handling, rate-limit Lua-script behavior via a real Redis test instance.
- Add a CI workflow (GitHub Actions) that runs lint + unit tests on every push, at minimum.
- Add a test (even a manual, documented runbook) that exercises `restore_from_backup()` against a disposable database before trusting it in `auto_rollover` mode.

#### Severity

**High.** This is the weakest category in the codebase by a wide margin, and it's the category most responsible for the other findings in this report existing undetected.

---

## 9. Production Readiness

**Score: 5.0 / 10**

#### What's done well

- Environment-driven configuration with a documented `.env.example` and a genuinely good secret-safety gate at startup (see Security).
- A real migration tool (Alembic) is wired up correctly, with both sync (`psycopg2`) and async (`asyncpg`) URLs handled cleanly in `migrations/env.py`.
- Backup and health-check services are present and configurable out of the box — most side projects at this stage have neither.
- `service_config.json` gives operators a single place to tune intervals/timeouts/retention without touching code.

#### What's below industry standard

- **No containerization.** There is no `Dockerfile` or `docker-compose.yml` anywhere in the repository, despite the app having three runtime dependencies (Postgres, Redis, `pg_dump`/`psql` binaries) that are exactly the kind of thing containers exist to standardize. `tools/scripts/setup_postgres.py` and `setup_redis.py` instead assume a bare Debian/Ubuntu host with `sudo`/`systemd` access, which is a materially less portable and less reproducible deployment story.
- **No CI/CD pipeline** of any kind (no `.github/workflows`, no equivalent). Nothing runs automatically on push — no lint, no tests, no build.
- **Backups are stored on the same local disk as the database** (`backups/`, relative to `PROJECT_ROOT`). A single-disk failure destroys both the live database and every backup simultaneously — there is no off-box/off-site copy step (S3, remote rsync, etc.).
- **No monitoring/metrics/alerting.** There is no `/metrics` (Prometheus) endpoint, no APM integration, and no external health endpoint distinct from the internal `dbhealthcheck` loop that an external load balancer or uptime monitor could poll. Operators would only learn about problems by tailing log files.
- No secrets-manager integration — secrets live in a plaintext `config/.env` file, which is standard for a $10 VPS deployment but worth flagging explicitly as a scaling limitation.
- No reverse-proxy/TLS-termination reference config (nginx/Caddy) even though `TRUSTED_PROXIES` and cookie `secure` flags clearly assume one exists in front of the app in production.

#### What a senior engineer would likely change

- Add a `Dockerfile` + `docker-compose.yml` (app + Postgres + Redis) for reproducible local dev and a real deployment artifact.
- Add a minimal GitHub Actions workflow: lint → unit tests → build.
- Add an off-box backup step (even a simple `rclone`/`aws s3 cp` push after each successful `pg_dump`).
- Expose a lightweight `/healthz` endpoint (no auth, no IP-block dependency) purely for load balancer/uptime-monitor use, decoupled from the internal auto-rollover logic.
- Add a sample nginx/Caddy config documenting the expected reverse-proxy setup (TLS termination, `X-Forwarded-For` trust) referenced implicitly by `TRUSTED_PROXIES`.

#### Severity

**Medium-to-High.** The application-level operational logic (backups, health checks) is genuinely ahead of many projects at this stage; the surrounding deployment infrastructure (containers, CI, off-box backups, monitoring) is essentially absent.

---

## 10. Professional Engineering Standards

**Score: 6.5 / 10**

#### Does this resemble hobby, junior, mid-level, senior, or production-grade code?

**Mid-level, with senior-leaning instincts in security and infrastructure design, held back by testing and operational maturity.**

This is not hobby code — hobby code doesn't implement peppered/salted/iterated password hashing with per-user upgrade paths, atomic Lua-script rate limiting, fail-closed authorization, or a supervised-restart background task framework. Those are the kinds of decisions that come from having seen systems fail in those specific ways before.

It is also not senior/production-grade code yet, for concrete, checkable reasons:

- A senior engineer's PR review would not have let the blocking-PBKDF2-in-the-event-loop issue (§7) merge as originally written — it directly contradicted the async architecture the rest of the code is built on. *(Since resolved — `verify_password` now offloads to a thread; see §7.)*
- A senior engineer would not accept a codebase with **zero unit tests** and no CI as "done," regardless of how good the manual smoke test is.
- The three divergent implementations of the same `cache_invalidating` concept (§2) were a classic mid-level pattern: the concept was understood, but it wasn't recognized as the *same* concept the second and third time it was needed, so it wasn't abstracted until later. *(Since resolved — see `src/models/crud/cache_invalidation.py`.)*
- Security fundamentals are strong, but the *surrounding* controls a senior engineer treats as non-negotiable at this privilege level — admin audit logging, MFA/IP-allowlisting for the highest-privilege API key — are missing (§5).

#### Signals that led to this conclusion

| Signal | Points toward |
|---|---|
| Fail-closed Redis dependency checks, secret-safety startup gate, peppered/salted iterated hashing | Senior-leaning security instincts |
| Atomic Lua scripts for rate limiting instead of naive read-modify-write | Senior-leaning correctness-under-concurrency awareness |
| Supervised background tasks with backoff, pre-restore safety backups | Senior-leaning reliability engineering |
| Blocking CPU-bound call inside an `async def` on the single event loop | Mid-level gap at the time — the async model wasn't fully internalized end-to-end. *(Since resolved — see §7.)* |
| Three copies of one concept instead of one shared abstraction | Mid-level gap — pattern recognition across files |
| Zero unit tests, no CI, no containerization, no monitoring | Testing/ops maturity has not yet caught up to the coding maturity |

---

## Concurrent User Capacity Estimates — $10 VPS, Single Node

**Assumptions stated explicitly**, since capacity estimates are meaningless without them:

| Assumption | Value |
|---|---|
| VPS tier modeled | Typical $10/mo tier (e.g. DigitalOcean/Linode/Vultr/Hetzner class): **1 shared vCPU, 1–2 GB RAM, SSD-backed** |
| Deployment | Postgres + Redis + the API process **all co-located on the same single node** (as this repo's tooling assumes) |
| Process model | Single Uvicorn process, **no `--workers`**, single asyncio event loop (as configured in `src/api/app.py`) |
| Traffic shape | "Concurrent users" = simultaneously active sessions making intermittent requests (typical admin-panel/API-consumer usage), **not** a raw sustained req/s benchmark |
| Bottleneck factored in (revised) | The blocking PBKDF2 call that dominated the original estimate (§7) **has since been fixed** — `verify_password` now offloads to a thread pool and no longer stalls the event loop. The remaining ceiling is ordinary resource contention: one shared vCPU serving Postgres, Redis, and the app's own event loop simultaneously, plus a single Uvicorn worker process (no `--workers`) still bounding how much of that capacity the request-handling path itself can use. |

> **Revised 2026-07-27:** the estimates below were originally built around the (now-fixed) blocking PBKDF2 call as the dominant bottleneck. With that fixed — and cookie authentication now also Redis-cached (§7) — the numbers below are revised upward from the original audit. They remain estimates, not benchmarks.

| Scenario | Estimated concurrent users | Reasoning |
|---|:---:|---|
| **Conservative** | **~250–400** *(was ~100–200)* | Ordinary resource contention on one shared vCPU serving Postgres, Redis, and the app together, plus Postgres pool limits (`pool_size=10` + `max_overflow=20`) under sustained write bursts. No longer capped by a single serialized, event-loop-blocking hash computation on every login. |
| **Realistic** | **~500–900** *(was ~300–600)* | Most traffic is cached reads — API-key permission checks and now cookie-validity checks both hit Redis, not Postgres — and logins/writes are a minority of traffic that no longer degrade unrelated requests when they occur. |
| **Optimistic** | **~1,500–2,000** *(was ~1,000–1,500)* | Best case: nearly all traffic is cache-hit reads, writes are rare, list endpoints aren't hammered. The ceiling is still set by the single Uvicorn worker process — this estimate assumes that process's own request-handling overhead (routing, serialization, I/O scheduling — not CPU-bound hashing, which is now threaded) stays the limiting factor rather than requiring a redesign. |

**The single highest-leverage change remaining** is running multiple Uvicorn worker processes behind a process manager (still viable on a $10 VPS with 1–2 cores) — since auth is already largely stateless (JWT + Redis + Postgres) and CPU-bound hashing no longer blocks the shared event loop, horizontal scaling of the API process itself is now a comparatively low-risk change with a real payoff, rather than one that would immediately run back into the blocking-call bug it previously depended on fixing first.

---

## Top 10 Strengths

1. **Fail-closed security defaults** — Redis unavailability returns `503`, never silently bypasses rate limiting or auth (`src/security/ip_block.py`, `api_security.py`, `cookie_security.py`).
2. **Startup secret-safety enforcement** — refuses to boot in production with default/placeholder secrets (`config/loader.py:_enforce_secret_safety`).
3. **Peppered + salted + iterated password hashing** with a per-user upgrade path (`hash_iterations`/`hash_algorithm` columns) already in the schema.
4. **Atomic Lua-script rate limiting and IP blocking** avoiding read-modify-write races under concurrency.
5. **Hybrid JWT + server-side revocation** for cookie sessions — solves real JWT revocation limitations without going fully stateful.
6. **Supervised background services** (`TaskSupervisor`) with exponential backoff and bounded restart attempts, applied uniformly.
7. **Thoughtful, layered backup/recovery design** — pre-restore safety backups, quarantined "bad backups," configurable leniency before drastic action.
8. **Correctly tuned async SQLAlchemy engine** (`pool_pre_ping`, `pool_recycle`, configurable pool sizing) — a detail many teams skip.
9. **Deliberate REST migration and privilege-escalation lockout** — SUPER_ADMIN keys cannot be minted over HTTP, closing an obvious escalation path.
10. **Clean, consistent layering** (api → security → crud → tables) with no handler ever touching the ORM directly.

## Top 10 Weaknesses

1. **✅ Resolved — blocking CPU-bound PBKDF2 call inside the async event loop** (`authenticate_password` → `verify_password`) has been fixed: `verify_password` now runs its hash computation via `asyncio.to_thread`, verified under a concurrency test not to stall unrelated in-flight requests.
2. **Zero unit tests and no CI pipeline** — only a live, infra-dependent smoke-test script exists.
3. **✅ Resolved — cookie authentication is now cached** in Redis (`_resolve_cookie_row()`), removing the Postgres round-trip on every cookie-authenticated request and closing the asymmetry with API-key authentication.
4. **✅ Resolved — three divergent implementations** of the `cache_invalidating` decorator concept across `user_crud.py`, `api_key_crud.py`, `auth_cookie_crud.py` have been consolidated into [`src/models/crud/cache_invalidation.py`](../src/models/crud/cache_invalidation.py).
5. **No containerization, CI/CD, or monitoring/metrics** — production deployment story is essentially a manual runbook.
6. **Backups stored on the same disk as the live database** — no off-box disaster-recovery copy.
7. **No pagination on list endpoints** (`GET /api/db/users`, `GET /api/db/keys`) — full-table scans returned as JSON.
8. **No admin audit log** — user/API-key admin actions are logged as text, not persisted queryably, and roll off after 7 days.
9. **Auth is invisible to OpenAPI** — `/docs` does not reflect that nearly every route requires a bearer token or cookie.
10. **No MFA/IP allowlisting for `SUPER_ADMIN` keys** — one leaked bearer token grants full user/API-key administration.

## The Biggest Architectural Concern

**Redis is a hard, fail-closed dependency for every single request in the system — including the unauthenticated root route (`/`), because `with_ip_block` runs before the handler on every decorated endpoint.** There is no circuit breaker, no degraded/local-fallback mode, and no distinction between "Redis is required for this route's core function" and "Redis is a nice-to-have cache here." A Redis process restart or brief network blip takes the **entire API offline**, even if PostgreSQL is perfectly healthy. On a single-node $10 VPS this is somewhat mitigated by the fact that the whole box goes down together anyway — but it becomes a real, avoidable single point of failure the moment Redis and the API are ever split across processes or hosts, which is the natural next scaling step.

## The Biggest Security Concern

**A single leaked `SUPER_ADMIN` bearer token is a full, silent compromise of user and API-key administration, with no secondary control and no forensic trail.** There is no MFA, no IP allowlisting, and no persisted audit log of who created or deleted which user/API key and from where — only ephemeral text log lines that roll off after 7 days. Given that this one credential can create arbitrary users, delete arbitrary users, and mint arbitrary lower-privilege API keys, it deserves defense-in-depth proportional to its power, which it currently does not have.

## The Biggest Scalability Concern

**✅ The originally-cited concern here — CPU-bound password hashing running synchronously inside the shared asyncio event loop — has been resolved** (`verify_password` now offloads via `asyncio.to_thread`; see §7). **The next biggest scalability concern:** the API still runs as a **single Uvicorn worker process with no `--workers`/multi-process deployment**. Even with the blocking-call bug fixed, this caps the request-handling path itself (routing, validation, JSON serialization, DB/Redis I/O scheduling) to one process — it cannot use more than one CPU core for that work, regardless of how many cores the VPS has. Auth is already largely stateless (JWT + Redis + Postgres), so running multiple worker processes behind a process manager is a comparatively low-risk, high-leverage change that hasn't been made yet.

## What Skills the Developer Should Focus On Next

1. **Async/await discipline end-to-end** — recognizing that "the function is `async def`" is not the same as "nothing in this call chain blocks the event loop." This was the most consequential finding in the original report (§7) and has since been fixed correctly, verified with a concurrency test. The underlying skill — auditing every call chain for accidental blocking calls, not just the one that got caught — is still the top area to keep sharpening: the same class of bug still exists in the lower-traffic `hash_password` call sites noted in §7.
2. **Automated testing culture** — unit and integration testing with fixtures/mocking (`pytest`, `pytest-asyncio`, a disposable test database), not just manual/live smoke scripts. This is the fastest way to have caught most of the other findings in this report before they shipped.
3. **Recognizing repeated patterns across files** *while writing them*, not after — the three `cache_invalidating` implementations (since consolidated into `src/models/crud/cache_invalidation.py`) were a symptom of writing each file in isolation rather than reaching for a shared abstraction the second time the need appeared.
4. **Operational/production engineering breadth** — containerization, CI/CD, monitoring/alerting, off-box backups. The application-level reliability engineering here (health checks, supervised tasks) is already strong; the surrounding "how does this actually get deployed and observed" layer is the clear next growth area.
5. **API contract discipline** — designing for consumers who only read `/docs`. This has since been demonstrated in practice: auth moved onto FastAPI `Depends()`, every route now declares `response_model=`, and a single consistent error envelope (`api_error()`) replaced the old bare-decorator/inconsistent-`detail` approach. The remaining growth area is applying the same discipline to *new* endpoints as the API surface grows, rather than letting contract drift creep back in.

## Estimated Engineering Level: **Mid-Level (upper)**

This codebase reflects a developer who has clearly studied and internalized several senior-level concerns — fail-closed security, atomic distributed rate limiting, supervised background services, secret hygiene — but has not yet fully internalized two things that separate mid-level from senior in practice: **(1)** verifying non-functional properties (does this async function actually stay async all the way down?) as rigorously as functional ones, and **(2)** treating automated testing and deployment infrastructure as first-class engineering deliverables rather than something to add later. On point (1): the specific blocking-PBKDF2 finding this report originally led with has since been fixed correctly and verified under a concurrency test — a genuinely good sign. On point (2): a senior engineer reviewing this repository would still block the PR on the absence of any automated test covering that fix (or any of the others made since this audit) before approving it for production traffic.

---

## Timeline: What Should Be Fixed, and When

| Timeframe | Focus | Concrete actions |
|---|---|---|
| **Immediate** (before any real traffic; hours-to-days of work) | Stop the bleeding on the two highest-severity findings | • **✅ Done:** `verify_password` now wraps its PBKDF2 call in `asyncio.to_thread(...)` (§7). Apply the same treatment to the remaining synchronous `hash_password(...)` call sites in the user-creation/password-rotation routes for full consistency. <br>• Add pagination (`limit`/`offset`) to `GET /api/db/users` and `GET /api/db/keys` (§3/§4). <br>• **✅ Done:** the dead `ratelimit_cache`/`ip_block_cache` config sections (§2) have been removed. <br>• Add a global FastAPI exception handler for unexpected exceptions so 500s are consistent. |
| **Short term** (next few weeks) | Testing and code-quality debt | • Stand up `pytest` + `pytest-asyncio` with a disposable Postgres test database; write unit tests for `security/tokens.py`, `security/validation/*`, and the CRUD layer first. <br>• Add a minimal GitHub Actions CI workflow (lint + unit tests) — even without full coverage, this catches regressions going forward. <br>• **✅ Done:** the three `cache_invalidating` implementations have been collapsed into one shared utility (`src/models/crud/cache_invalidation.py`). <br>• **✅ Done:** authentication moved onto FastAPI `Depends()` so `/docs` reflects reality; `response_model=` added to every route; a single error envelope (`api_error()`) unified all `HTTPException` details. |
| **Medium term** (1–3 months) | Cache parity, ops maturity, audit trail | • **✅ Done:** Redis caching for `auth_cookies` validity has been added, mirroring the existing API-key permission cache (§7). <br>• Add a persisted admin audit log table for user/API-key mutations. <br>• Add a `Dockerfile` + `docker-compose.yml` for app/Postgres/Redis, and an off-box backup step (e.g., push `pg_dump` output to S3/remote storage after each successful run). <br>• Add a `/healthz` endpoint decoupled from the internal auto-rollover health check, for external load balancers/uptime monitors. |
| **Long term** (3–6+ months, as real traffic materializes) | Hardening and horizontal scale | • Add MFA or IP allowlisting for `SUPER_ADMIN` API keys. <br>• Add CSRF protection before any real cookie-authenticated mutation route ships. <br>• Introduce a normalized roles/permissions table if role complexity grows beyond a flat string array. <br>• Run multiple Uvicorn workers behind a process manager/load balancer once the blocking-call fix is verified, and revisit Postgres pool sizing accordingly. <br>• Evaluate a migration path from PBKDF2 to Argon2id using the existing per-user `hash_algorithm` column as the versioning mechanism. |
