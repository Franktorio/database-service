# API / DB Expansion Format

Use this document when adding a new endpoint family or a new database-backed feature.

## API Folder Shape

```text
src/api/system/<feature_name>/
  models.py
  routes/
    __init__.py
    router.py
    _get_routes.py
    _post_routes.py
    _patch_routes.py        # when updates exist
    _delete_routes.py       # when deletes exist
```

## Database Folder Shape

```text
src/models/tables/system/<feature_table>.py
src/models/crud/system/<feature_table>_crud.py
```

## Current Conventions

- Register routers in `src/api/app.py`.
- Use `with_ip_block` on externally reachable endpoints.
- Use `api_authentication` for API-key authorization checks.
- Use `cookie_authentication` for cookie/JWT session checks.
- Keep request models close to the route family they serve.
- Keep table registration explicit through `src/models/tables/__init__.py`.
- Prefer CRUD helpers that accept an optional async session for transaction composition.

## Validation Expectations

- Validate rate limits as positive integers.
- Validate permission levels against the constants in `src/api/config.py`.
- Be explicit about whether secrets are passed in query parameters, headers, cookies, or JSON bodies.
- If a table is expected to support ordered retrieval, expiry sweeps, or high-frequency lookup, declare the supporting index in the model.

## Documentation Expectations

- Update `README.md` when the public surface or deployment behavior changes.
- Update `docs/API.md` when endpoints, methods, auth semantics, or payloads change.
- Update `docs/DB.md` when schema, indexes, migration behavior, or operational assumptions change.
- Update `docs/ENGINEERING_REVIEW_2026-07-26.md` when a major audit materially changes the current assessment.
