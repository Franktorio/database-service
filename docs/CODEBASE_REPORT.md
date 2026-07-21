# Full Codebase Report

## Report Metadata

- Date: 2026-07-21
- Basis: current `main` branch at HEAD (`d571020`)
- Review type: static code audit + diagnostics review
- Runtime status: not benchmarked in this pass

This report supersedes prior versions and is a full current-state assessment.

## Scope

This review covers:

- Startup/bootstrap and service lifecycle
- Config loading and environment controls
- API contracts and request validation
- API key auth and cache invalidation behavior
- Password and cookie auth flows
- Rate limiting and IP blocking
- Database schema, CRUD, and index usage
- Healthcheck/backup/restore services
- Migration scripts and operational safety
- Documentation accuracy vs code behavior

## Executive Summary

The codebase is improving quickly and several previously high-risk issues were fixed. The overall architecture remains clear and maintainable for a single-node service. However, one new critical regression in the healthcheck module can break service startup, and there are still important correctness/operations gaps that keep this below production-grade industry standards.

In plain terms:

- Direction: better than last audit.
- Immediate risk: still high due to one startup-breaking import issue.
- Capacity class: unchanged (small to moderate single-node workload).

## What Was Fixed Since The Previous Audit

1. API model validation improved.
- Pydantic `Field(...)` constraints and metadata were added across request models.
- This is a major step toward predictable contract behavior.

2. API-key cache freshness improved.
- Update/delete key flows now invoke ratelimiter refresh/removal helpers.
- Stale in-memory authorization risk after key changes is reduced.

3. Cookie auth consistency improved.
- Login and refresh now rely on shared cookie settings (`get_cookie_settings`).
- Token hash refresh now migrates limiter state (partially lock-protected).

4. User creation response bug fixed.
- The response no longer references a nonexistent `initial_role` attribute.

5. SQL echo behavior improved.
- SQLAlchemy engine echo is now tied to development mode.

6. DB healthcheck strategy changed.
- Healthcheck moved from `pg_isready`-style probing to actual DB query checks.
- This is directionally better for functional availability checks.

## Current High-Risk Findings (Most Important First)

### 1) Critical: `dbhealthcheck` imports a symbol that does not exist

Files:

- `src/services/dbhealthcheck.py`
- `config/loader.py`

Details:

- `dbhealthcheck.py` imports `AsyncSessionLocal` from `config.loader`.
- `config.loader` does not define `AsyncSessionLocal`.
- Service-layer imports `dbhealthcheck` at module import time.

Impact:

- Can fail startup with import error before API begins serving.
- This is an immediate release blocker.

Suggested fix:

- Import `SessionLocal` from `src/models/database.py` instead.
- Optionally alias: `from src.models.database import SessionLocal as AsyncSessionLocal`.
- Add a startup smoke test that imports `main` and starts dependency graph without running server.

### 2) High: `refresh_ratelimiter` has async misuse in fallback path

Files:

- `src/security/api_security.py`

Details:

- `refresh_ratelimiter` is synchronous.
- Fallback path calls `get_api_key(api_hash)` without `await`.
- This returns a coroutine, not an `ApiKey` object.

Impact:

- Current route path passes `api_object`, so it often works.
- Any future caller relying on fallback path may crash or silently misbehave.

Suggested fix:

- Remove fallback path entirely and require `api_object: ApiKey`.
- Or make `refresh_ratelimiter` async and properly await DB lookup.
- Add type checks/assertion to prevent coroutine leakage.

### 3) High: Permission-level validation constraints conflict with actual permission map

Files:

- `src/api/system/api_db_endpoints/models.py`
- `src/api/config.py`

Details:

- Permission constants are 0..4 (`VIEW_LEVEL=0`, `SUPER_ADMIN_LEVEL=4`).
- Request model currently enforces `ge=1, le=5`.
- Default value is `VIEW_LEVEL` (0), which conflicts with `ge=1` semantics.

Impact:

- View-level key creation can be incorrectly blocked.
- Undefined permission `5` is allowed by model constraints.

Suggested fix:

- Set constraints to `ge=VIEW_LEVEL` and `le=SUPER_ADMIN_LEVEL`.
- Optionally validate with `Literal[0,1,2,3,4]` or enum-backed type.

### 4) Medium-High: Cookie ratelimiter migration still not fully lock-safe

Files:

- `src/security/cookie_security.py`

Details:

- One part of migration (`pop`) is now under `_cache_lock`.
- Follow-up writes (`_last_seen_by_token.pop` and `_place_in_ratelimiters`) occur outside the lock.

Impact:

- Race windows still exist under concurrent requests.
- Could cause intermittent limiter drift/loss.

Suggested fix:

- Move full migration sequence under one lock.
- Use a single helper like `_move_ratelimiter(old_hash, new_hash, old_limit)` guarded by `_cache_lock`.

### 5) Medium-High: Healthcheck restore flow still operationally risky

Files:

- `src/services/dbhealthcheck.py`

Details:

- Restore still replays SQL into the active DB.
- Automatic repeated restore attempts can escalate damage during logical corruption or bad backup chains.

Impact:

- Potential compounding data integrity issues under failure conditions.

Suggested fix:

- Add explicit safety gate: `allow_auto_restore=false` default in production.
- Validate candidate backup with dry-run checks before restore.
- Prefer restore into clean target and controlled switchover procedure.

## Remaining Important Findings

### Startup lifecycle risks

Files:

- `main.py`
- `src/api/app.py`

Details:

- Background threads start before API lifespan initializes DB schema.
- If API disabled, daemon threads do not provide persistent worker behavior.

Suggested fix:

- Initialize DB and validate service dependencies first.
- Start long-lived workers under explicit supervisor semantics.

### Database connection URL safety

Files:

- `config/loader.py`

Details:

- DB password is interpolated directly into URL without URL-encoding.

Suggested fix:

- Build URL with SQLAlchemy URL helpers or quote password safely.

### Distributed behavior limitations

Files:

- `src/security/api_security.py`
- `src/security/cookie_security.py`
- `src/security/password_security.py`
- `src/security/ip_block.py`

Details:

- All abuse controls are process-local in-memory caches.

Suggested fix:

- Move limiter/block state to shared backend (Redis or DB with lease strategy) if horizontal scaling is needed.

### Migration script safety gaps

Files:

- `scripts/migrate_db.py`

Details:

- Compatible-column copy still silently skips incompatible columns.
- Sequence reset safety remains unverified.

Suggested fix:

- Add explicit post-copy sequence reconciliation.
- Fail migration on critical compatibility mismatches unless explicitly allowed.

### API documentation drift

Files:

- `docs/API.md`
- `README.md`

Details:

- User creation docs still describe `role`, but API now expects `initial_role`.
- README still lists `JWT_COOKIE_NAME` as env, while code now uses `COOKIE_JWT_INDEX` constant.

Suggested fix:

- Update docs to reflect active request models and current cookie-key source.

## Strengths (Current)

1. Strong modular layout.
- Clear separation between API, security, CRUD, model, and service layers.

2. Security baseline is decent for a small service.
- Secret checks in non-development mode.
- Token hashing for API keys and cookie tracking.

3. Indexing posture improved.
- Useful indexes exist on key auth/log paths.

4. Fix velocity is high.
- Recent commits show active hardening and response to findings.

## Weaknesses (Current)

1. Operational safety still lags.
- Healthcheck/restore automation remains risky.

2. Contract consistency is improving but fragile.
- Validation bounds and permission semantics still misaligned.

3. Shared-state assumptions limit scale.
- In-memory limiter/block state is single-process only.

4. Test guardrails are still not visible.
- Regressions can slip into critical auth/admin paths.

## Updated Priority Roadmap

### Priority 0 (Do Now)

1. Fix `AsyncSessionLocal` import break in healthcheck.
2. Fix `refresh_ratelimiter` fallback async misuse.
3. Correct permission validation bounds to 0..4 map.

### Priority 1

4. Fully lock cookie ratelimiter migration.
5. Add startup smoke test + auth/admin contract tests.

### Priority 2

6. Harden restore policy and add safer recovery gates.
7. Resolve doc drift (`initial_role`, cookie key behavior).

### Priority 3

8. Improve DB URL construction safety.
9. Add migration post-copy sequence resets and strict mismatch policy.
10. Plan shared-state backend for abuse controls if multi-instance deployment is expected.

## Suggested Fixes (Concrete)

### Fix Set A (Startup + auth correctness)

- `src/services/dbhealthcheck.py`
  - Replace import source with `SessionLocal` from `src/models/database.py`.
  - Use that session factory in `database_query_check`.
- `src/security/api_security.py`
  - Refactor `refresh_ratelimiter` to require `api_object` and remove fallback DB fetch.
- `src/api/system/api_db_endpoints/models.py`
  - Set `permission_level` and `new_permission_level` bounds to 0..4 (or constants-driven).

### Fix Set B (Concurrency + operational resilience)

- `src/security/cookie_security.py`
  - Make token-hash ratelimiter migration atomic under `_cache_lock`.
- `src/services/dbhealthcheck.py`
  - Add `auto_restore_mode` with safer defaults (`disabled` or `manual-confirm`) for production.
  - Add backup validation and explicit alert path before restore attempts.

### Fix Set C (Reliability guardrails)

- Add tests for:
  - API-key update path including ratelimiter refresh.
  - User create with `initial_role` payload.
  - Cookie refresh preserves effective ratelimit state.
  - App import/startup smoke path catches module import breakages.

## Capacity Estimate (Revalidated)

Assumptions:

- Single uvicorn worker
- 2-4 vCPU
- local/same-LAN PostgreSQL
- default logging and persistent auth event writes enabled

Estimated envelope:

- API-key admin read-heavy traffic: ~100-250 req/s
- Cookie-auth-heavy flows: ~30-80 req/s
- Typical concurrently active users: tens to low hundreds

Reason estimate did not increase:

- Bottlenecks remain mostly architectural (in-memory control state, DB writes on auth path, single-process assumptions), not just micro-bugs.

## Industry Standards Comparison

Where this now aligns better:

- Better request validation discipline.
- Better cache invalidation behavior for API-key lifecycle.
- Better development-vs-production SQL logging defaults.

Where it is still behind mature production systems:

- Startup and recovery safety guarantees.
- End-to-end automated testing for auth/admin critical paths.
- Distributed limiter/blocking strategy.
- Migration rigor and recovery orchestration.
- Documentation-to-code synchronization discipline.

## Bottom Line

The codebase is trending in the right direction and is materially better than in the previous audit. The new healthcheck import break is the top blocker and should be fixed immediately. After that, a focused hardening pass on validation consistency, limiter concurrency, and restore safety will give the largest risk reduction per effort.
