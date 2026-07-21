# Full Codebase Report

## Report Metadata

- Date: 2026-07-21
- Basis: current `main` branch at HEAD (`6061b35`)
- Review type: static code audit + docs drift audit
- Runtime status: service entrypoint starts (`python3 main.py` exited 0), no load test in this pass

This report supersedes prior versions and reflects current code and docs state after the latest fixes.

## Scope

This pass reviewed:

- Startup lifecycle and service orchestration
- API request models and endpoint behavior
- API key and cookie auth/rate-limit flows
- Database initialization/index coverage
- Healthcheck/restore safety behavior
- Documentation consistency across README/API/DB/report

## Executive Summary

The project has improved materially over the previous audits. Several high-priority items were fixed: permission bounds now align to constants, healthcheck uses `SessionLocal`, and cookie-ratelimiter migration is now lock-atomic via a dedicated move helper.

The API key update runtime regression identified in the previous pass (`refresh_ratelimiter` signature mismatch) has now been fixed. Immediate correctness risk has dropped, and the remaining work is mostly operational hardening and scale-oriented architecture.

Overall:

- Architecture quality: solid for a compact single-node service.
- Immediate release risk: medium, primarily due to recovery/lifecycle hardening gaps.
- Capacity class: small to moderate single-node administrative workload.

## What Was Fixed Since Prior Reports

1. Healthcheck import/session usage corrected.
- `dbhealthcheck` now imports and uses `SessionLocal` from the database layer.
- Prior startup import-break risk appears resolved.

2. Permission-level model constraints corrected.
- API key request models now use `ge=VIEW_LEVEL` and `le=SUPER_ADMIN_LEVEL`.
- This aligns request validation with actual permission constants (0..4).

3. Cookie ratelimiter migration hardened.
- Token-hash migration now uses a lock-guarded move helper.
- Prior partial-lock race concern was reduced significantly.

4. User create contract cleanup retained.
- Route response no longer references the removed `initial_role` attribute.
- Request model still correctly uses `initial_role` as input.

5. SQL echo behavior remains correctly scoped.
- Engine echo is tied to development mode rather than always-on.

6. API key update cache refresh regression fixed.
- `update_key` now calls `refresh_ratelimiter(updated_api_key)` with the correct signature.
- Runtime `TypeError` risk on the API key update path is removed.

## Current Findings (Ordered by Severity)

### 1) Medium-High: Recovery automation can still amplify bad-state incidents

File:

- `src/services/dbhealthcheck.py`

Details:

- Restore logic can attempt replay from backup directly into active DB.
- Automatic reparations loops are bounded, but still operate without backup integrity verification.

Impact:

- In some corruption/failure scenarios, automatic restore attempts may worsen operational recovery complexity.

Suggested fix:

- Keep `auto_rollover=false` as production default.
- Add backup verification gate before restore.
- Consider restore-to-staging then controlled switchover for production-grade recovery.

### 2) Medium: Startup lifecycle ordering remains fragile

Files:

- `main.py`
- `src/api/app.py`

Details:

- Background service threads start before API lifespan initializes schema/indexes.
- Some services can begin work while DB init has not completed.

Impact:

- In edge startup timing scenarios, services may race with DB initialization.

Suggested fix:

- Initialize DB earlier in bootstrap flow, or gate service start on successful DB init completion.

### 3) Medium: DB URL construction does not encode credentials

File:

- `config/loader.py`

Details:

- Password is interpolated directly into DSN string.
- Special characters in credentials can break connection parsing.

Suggested fix:

- Build URL with SQLAlchemy URL helpers or URL-encode credential components.

### 4) Medium: Single-process limiter/blocking architecture limits horizontal scale

Files:

- `src/security/api_security.py`
- `src/security/cookie_security.py`
- `src/security/password_security.py`
- `src/security/ip_block.py`

Details:

- Abuse-control state is process-local in memory.
- Multi-instance deployments will have inconsistent enforcement.

Suggested fix:

- Move limiter/block state to a shared backend (for example Redis) when scaling beyond one process/node.

## Strengths

1. Clean modular organization.
- Clear separation of API, security, model, CRUD, and service layers.

2. Better validation discipline.
- Pydantic field constraints now cover key API admin/user request surfaces.

3. Index posture is now practical.
- Added indexes align with known query and cleanup paths for system tables.

4. Security baseline is reasonable for this size.
- Token hashing, secret safety checks, and persistent auth logging are all present.

5. Fast remediation velocity.
- Recent commits show consistent response to audit findings.

## Capacity Estimate (Current)

Assumptions:

- Single Uvicorn process
- 2-4 vCPU
- PostgreSQL on same host or low-latency LAN
- Persistent logging enabled

Estimated envelope:

- API-key-heavy admin traffic: ~100-250 req/s
- Cookie-auth-heavy flows: ~30-80 req/s
- Typical concurrently active users: tens to low hundreds

Why this range remains limited:

- Synchronous control-plane dependencies on DB writes for auth logging
- Process-local limiter/blocking state
- `NullPool` connection behavior and single-node execution assumptions

## Industry Comparison

Where this service aligns with good practice:

- Clear boundary separation and readable codebase structure
- Stronger input validation than in earlier iterations
- Explicit table/index declarations with startup convergence

Where it still trails mature production systems:

- Startup ordering guarantees and lifecycle orchestration
- Recovery safety controls and restore discipline
- Distributed abuse-control design
- Automated regression testing depth for critical auth/admin paths

## Updated Priority Roadmap

### Priority 0 (Immediate)

1. Add one regression test for `/api/db/keys/update` successful update path.
2. Add one startup smoke test that exercises service import and initialization ordering.

### Priority 1

3. Harden restore flow with verification gates and safer operational mode.
4. Gate background service startup on confirmed DB initialization.

### Priority 2

5. Make DB URL construction robust for special characters.
6. Add migration safety checks for sequence reconciliation and strict compatibility policy.

### Priority 3

7. Design shared limiter/block state backend for multi-instance deployments.
8. Add broader auth/load characterization tests.

## Documentation Status

Docs were updated in this pass to match current behavior:

- README now reflects development-only SQL echo and removed stale cookie-setting mismatch claim.
- API docs now use `initial_role` in user-create examples.
- DB docs now describe development-only SQL echo.

## Reflection

This is the first pass where the codebase moved from "active correctness regressions" to mostly "operational maturity gaps." The remediation pattern is working: issues are being fixed quickly and safely with targeted changes. The next quality jump will not come from more endpoint tweaks, but from guardrails (tests) and safer failure-recovery controls.

## Bottom Line

The codebase is trending positively and is substantially cleaner than earlier snapshots. The prior API key update regression has been resolved. The highest-value remaining work is restore-flow hardening, startup lifecycle gating, and adding regression tests to preserve the current pace of improvement.
