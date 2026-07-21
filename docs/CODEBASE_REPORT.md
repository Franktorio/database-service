# Full Codebase Report

## Scope

This report updates the prior audit using the repository state on 2026-07-21. It focuses on what changed since commit 44582af, re-scores priorities, and adds concrete fix suggestions.

Review method:

- Read-only source inspection of modified files since 44582af.
- Validation of editor diagnostics (`get_errors`) on key changed modules.
- No runtime integration test execution in this pass.

## What You Fixed Since The Last Report

These issues are now materially improved:

1. Cookie/JWT config consistency improved.
- Cookie settings are now centralized through `get_cookie_settings` and used by login and refresh flows.
- Cookie key usage now converges on `COOKIE_JWT_INDEX` instead of split naming.

2. API key cache invalidation improved.
- API key delete/update flows now call ratelimiter cache management functions.
- This reduces stale authorization behavior after key changes.

3. SQL echo behavior improved.
- DB engine echo now depends on operating mode (`development` only), which is closer to sane production defaults.

4. Cookie ratelimit bypass from token rotation was partially addressed.
- You now migrate ratelimiter state to the new token hash during refresh, which is directionally correct.

5. User creation semantics are cleaner.
- User create now explicitly uses a single initial role (`initial_role`) instead of ambiguous role array entry semantics.

## New Or Remaining High-Risk Findings

## 1) High: API key update route can crash on first successful update

Location:

- `src/api/system/api_db_endpoints/routes/_post_routes.py`
- `src/security/api_security.py`

Issue:

- Route calls `refresh_ratelimiter(updated_api_key.key_hash, updated_api_key.rate_limit)`.
- `refresh_ratelimiter` in `api_security.py` currently accepts a single `ApiKey` object, not `(key_hash, rate_limit)`.
- First successful update request will likely raise `TypeError` at runtime.

Impact:

- Admin key update endpoint can fail post-DB update, creating control-plane inconsistency.

Suggested fix:

- Pick one API contract and enforce it everywhere.
- Recommended: keep `refresh_ratelimiter(api_key: ApiKey)` and call `refresh_ratelimiter(updated_api_key)` from route.
- Add a focused endpoint test for update flow to catch signature drift.

## 2) High: create-user response references non-existent model field

Location:

- `src/api/system/user_db_endpoints/routes/_post_routes.py`
- `src/models/tables/system/user_table.py`

Issue:

- Response payload includes `created_user.initial_role`.
- User model does not expose `initial_role`; it stores `roles` and derived `role` property.

Impact:

- Successful user creation can throw runtime attribute error when forming response.

Suggested fix:

- Replace `initial_role` response field with `role` (or first element of `roles`).
- Add create-user response schema test to ensure all returned attributes exist.

## 3) High: Cookie ratelimiter state migration is not lock-protected

Location:

- `src/security/cookie_security.py`

Issue:

- Ratelimiter transfer from old token hash to refreshed token hash mutates shared maps without `_cache_lock`.
- Under concurrency, this can race and produce dropped/misaligned limiter entries.

Impact:

- Intermittent authorization throttling bugs; difficult production-debug profile.

Suggested fix:

- Wrap pop/insert migration block in `with _cache_lock:`.
- Prefer a dedicated helper `move_cookie_ratelimiter(old_hash, new_hash)` that is lock-safe and unit-tested.

## 4) High: Healthcheck and restore safety issues remain

Location:

- `src/services/dbhealthcheck.py`

Issue:

- Prior high-risk concerns still appear unresolved:
  - Health check may conflate auth/connectivity conditions with true DB health.
  - Auto restore still appears risky for in-place replay scenarios.

Impact:

- Potential self-inflicted outages or data integrity risk during transient DB incidents.

Suggested fix:

- Split liveness from readiness checks and make restore/manual intervention opt-in by default.
- Add explicit preflight checks and dry-run mode before any restore action.

## 5) Medium-High: Input validation gaps still allow unsafe rate-limit values

Location:

- `src/api/system/api_db_endpoints/models.py`
- `src/api/system/user_db_endpoints/models.py`

Issue:

- Models still rely on plain `int` fields without lower bounds.
- Zero/negative values can still propagate into runtime limiter logic.

Impact:

- Unstable throttling behavior and possible divide-by-zero style edge paths.

Suggested fix:

- Add Pydantic constraints, e.g. `Field(ge=1)` for limits and sensible upper bounds.
- Add validation error tests for boundary values.

## Re-Shifted Priority Order

### Priority 0: Fix newly introduced runtime regressions first

1. Route/function signature mismatch in API-key update flow.
2. `created_user.initial_role` response bug in user create flow.

Reason:

- These are direct request-path breakages that can surface immediately in production/admin usage.

### Priority 1: Stabilize concurrency and auth correctness

3. Lock-safe cookie ratelimiter migration.
4. Add tests for cookie refresh + limiter continuity under concurrent requests.

### Priority 2: Reduce operational blast radius

5. Harden DB healthcheck signal quality and recovery behavior.
6. Keep destructive restore path disabled by default unless explicitly enabled.

### Priority 3: Tighten validation and contract safety

7. Add Pydantic constraints for rate limits and permission levels.
8. Add typed response models for key admin endpoints to detect field drift automatically.

### Priority 4: Continue structural maturity work

9. Migrate from ad-hoc migration script to formal migration tooling.
10. Introduce proxy-aware client IP handling and structured observability.

## Additional Suggestions (Practical)

1. Add a small contract-test suite for the critical admin flows.
- `POST /api/db/keys/update`
- `DELETE /api/db/keys/delete`
- `POST /api/db/users/create`
- `POST /login-auth-test` and `POST /cookie-auth-test`

2. Add a pre-commit/runtime smoke check in CI.
- Run lint/type checks and a minimal API integration subset.
- Catch route/signature mismatches before merge.

3. Move shared cache operations behind helper APIs.
- Avoid direct map mutations from multiple modules.
- Enforce lock discipline and consistent semantics.

4. Add a change log section in this report per audit update.
- Helps show which issues are closed, downgraded, or newly introduced over time.

## Updated Capacity View

Your recent fixes improve reliability and reduce some accidental auth drift, but the overall capacity class is unchanged because the main bottlenecks remain:

- Process-local state for abuse controls.
- DB writes in auth hot paths.
- Single-process assumptions.

Reasonable current estimate still stands:

- ~100-250 req/s for simple API-key admin read-heavy traffic.
- ~30-80 req/s for cookie-auth-heavy flows.
- Tens to low hundreds of concurrently active users on a modest single node.

## Industry-Standard Comparison (Updated)

Improved relative to previous state:

- Better key/cookie consistency.
- Better cache invalidation behavior for API key lifecycle.
- Better production log-noise posture.

Still below mature production standard in key areas:

- No comprehensive automated tests guarding critical auth/admin paths.
- No distributed/shared throttling state.
- Recovery automation still risk-prone.
- Migration safety model is still ad-hoc.

## Recommended Immediate Patch Set

If you want the fastest safety win in one PR:

1. Fix `refresh_ratelimiter` route call signature.
2. Replace `created_user.initial_role` with `created_user.role` in response.
3. Add lock around cookie ratelimiter transfer block.
4. Add request-model validation bounds for all rate-limit fields.
5. Add 4 focused API tests for create-user, update-key, delete-key, and cookie refresh continuity.

This single bundle would meaningfully lower your current operational risk.
