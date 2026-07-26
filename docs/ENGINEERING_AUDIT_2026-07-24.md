# Engineering Audit Report

Date: 2026-07-26
Repository: clean-database-service
Scope: Current workspace state after merge-recovery pass

## Executive Summary

The codebase is functional and shows solid practical engineering progress, but it is still below full production-grade reliability and governance standards.

During this pass, merge-related regressions in service supervision were reviewed and one confirmed runtime regression was restored in API lifespan handling:

- supervised services now always start during lifespan startup (not only when an external ready-signal object is present)
- supervised service cancellation is now awaited during shutdown, restoring graceful teardown behavior

Overall posture:

- Architecture: good modular boundaries with improving async orchestration
- Security: decent baseline controls, but custom JWT implementation and operational secret handling remain risks
- Reliability: meaningful safety features exist, but healthcheck recovery strategy still carries high blast radius
- Testing: still the largest gap

## What Was Reviewed

Recent commits reviewed (focus: merge recovery, supervisor, operating-mode wiring):

- 1ee42b0 (merge-fix commit)
- f922c2c
- 65512b3
- Selected earlier baselines tied to orchestration changes

High-signal files reviewed:

- main.py
- config/loader.py
- src/api/app.py
- src/services/supervisor.py
- src/services/system/backup.py
- src/services/system/dbhealthcheck.py
- src/models/database.py
- src/security/tokens.py
- config/service_config.json

## Merge-Recovery Findings And Restorations

### Restored

1. Lifespan task startup regression
- Problem: background supervisors were only started inside a DB-ready-signal conditional branch.
- Impact: when app booted without that signal object, background services never started.
- Restoration: supervisor start loop now runs unconditionally once services are registered.

2. Lifespan shutdown regression
- Problem: async `TaskSupervisor.cancel()` was called without awaiting.
- Impact: cancellation could be skipped or left incomplete during shutdown.
- Restoration: cancellation is awaited via `asyncio.gather(..., return_exceptions=True)`.

### Not Restored (No Trustworthy Recovery Source In Reachable History)

- No additional operating-mode/supervisor behavior could be safely reconstructed beyond what exists in reachable commit history.
- If there are missing behaviors from lost/unreachable commits (force-push fallout), they are not recoverable from local branch history alone and need either:
  - another clone/remote reflog source, or
  - explicit behavior specs to re-implement directly.

## Current Architecture Assessment

Score: 6.5/10

Strengths:

- Clear modular layout across API, security, models, services, and config.
- FastAPI lifespan is now the dominant runtime orchestrator.
- Supervisor abstraction centralizes restart policy and retry backoff.

Risks:

- Recovery and shutdown behavior still rely on in-process control flow.
- Some service-state coupling remains implicit (signal-driven assumptions).

## Runtime Orchestration Assessment

Score: 6/10

Current behavior:

- API lifespan initializes DB connectivity.
- Service loops (cookie expiry, backup, healthcheck) are supervised by `TaskSupervisor`.
- Shutdown now correctly awaits supervised task cancellation and then closes Redis and DB engine.

Gaps:

- Restart policy catches a narrow exception set in supervisor; unknown exception classes may bypass intended retry semantics.
- There is no external watchdog/orchestrator contract documented for terminal service failures.

## Operating Mode And Config Assessment

Score: 7/10

Strengths:

- Explicit operating-mode constants are present.
- Non-development mode secret safety checks are enforced at startup.
- API test endpoint exposure is mode-sensitive.
- Supervisor retry controls are configurable from environment.

Gaps:

- Runtime behavior differences by mode are still distributed across modules rather than centralized policy.
- Missing config schema validation layer (current checks are handcrafted).

## Data Layer Assessment

Score: 7/10

Strengths:

- Async SQLAlchemy engine/session setup is coherent.
- Pool settings are configurable and enabled.
- DB init now verifies connectivity without mutating schema at startup.

Gaps:

- Alembic is present but revision discipline is still immature (`alembic/versions` effectively unused).
- Transaction ownership remains fragmented in deeper CRUD chains.

## API And Contract Assessment

Score: 6/10

Strengths:

- Route separation is clear across system API key and user endpoints.
- Auth/rate-limit middleware patterns are reused consistently.

Gaps:

- API remains mostly RPC-shaped (`/create`, `/update`, `/delete`, `/list`).
- Response envelope conventions are mixed.
- Versioning/deprecation policy is not formalized.

## Security Assessment

Score: 6/10

Strengths:

- Password hashing uses PBKDF2 with salt + pepper.
- API keys/tokens are hashed at rest.
- Mode-aware secret safety checks reduce accidental insecure deployments.

Gaps:

- JWT implementation is custom and should be replaced with a hardened library.
- Operational scripts still require careful secret handling discipline.
- CSRF posture for future cookie-authenticated state-changing endpoints is not explicit.

## Reliability And Recovery Assessment

Score: 5/10

Strengths:

- Healthcheck service supports leniency and optional auto-rollover.
- Backup service has retention and timeout controls.
- Core runtime now has supervised service restart behavior.

High-risk concerns:

- Healthcheck auto-rollover can perform destructive drop-and-restore operations in-process.
- Failure path still includes hard process termination (`SIGINT`) under critical conditions.
- Logging queue overflow can silently drop messages.

## Testing And Delivery Assessment

Score: 3.5/10

Strengths:

- Live end-to-end system test exists and covers major flows.

Gaps:

- No meaningful unit/integration test pyramid.
- No CI pipeline enforcing regression checks.
- No release gates tied to migrations, rollback plans, or smoke checks.

## Production Readiness Scorecard

| Category | Score (1-10) | Risk Level |
|---|---:|---|
| Architecture | 6.5 | Medium |
| Runtime Orchestration | 6.0 | Medium |
| Operating Mode / Config | 7.0 | Medium |
| Data Layer | 7.0 | Medium |
| API Contract Design | 6.0 | Medium |
| Security | 6.0 | High |
| Reliability / Recovery | 5.0 | High |
| Testing / Delivery | 3.5 | High |
| Production Readiness (Overall) | 5.8 | High |

## Top Risks To Address Next

1. Add focused regression tests for lifespan startup/shutdown supervision behavior.
2. Replace custom JWT implementation with a vetted library and explicit claim validation policy.
3. Redesign healthcheck auto-rollover so destructive restore operations are operator-mediated or isolated.
4. Expand supervisor exception handling strategy and terminal-failure visibility.
5. Build CI with minimum gates: lint, type checks, critical unit tests, and one integration smoke path.
6. Establish Alembic revision workflow with committed migrations and deployment procedures.

## Suggested 14-Day Stabilization Plan

1. Day 1-2
- Add tests for `src/api/app.py` lifespan startup/shutdown paths.
- Add tests for `src/services/supervisor.py` restart/cancel semantics.

2. Day 3-5
- Migrate token handling to a standard JWT library.
- Preserve current claims while adding strict validation behavior.

3. Day 6-8
- Harden dbhealthcheck failure strategy to avoid automatic destructive restore in default mode.
- Add explicit operator override flags for restore actions.

4. Day 9-11
- Add CI workflow for lint/tests and fail-on-regression checks.
- Add smoke-test workflow against ephemeral Postgres/Redis.

5. Day 12-14
- Generate and commit first Alembic revisions for current schema baseline.
- Document migration + rollback process.

## Final Verdict

This repository reflects strong iterative engineering effort and is moving in the right direction. The supervision merge regression has been repaired in current workspace code. The biggest blockers to senior-grade production posture remain test depth, recovery safety design, and release governance.
