# API Reference

The API service currently exposes two layers:

1. Root and auth checks in `src/api/app.py`.
2. Super-admin API-key administration in `src/api/api_db_endpoints/`.

## Current Admin Surface

- `GET /` returns a service greeting.
- `POST /auth-test` validates the supplied API key and echoes the resolved permissions.
- `GET /api/db/keys` returns a simple health message for the API-key admin surface.
- `POST /api/db/keys/list` lists stored API keys.
- `POST /api/db/keys/create` creates a new API key.
- `POST /api/db/keys/update` updates an API key by `key_hash`.
- `DELETE /api/db/keys/delete` deletes an API key by `key_hash`.

## Authorization

All API-key admin endpoints require `SUPER_ADMIN_LEVEL` access. The bootstrap SUPER_ADMIN key is intended to be created from `scripts/generate_api_key.py`.

## Expansion Pattern

When adding a new API surface:

1. Create a new router package under `src/api/`.
2. Define request models close to the routes that use them.
3. Register the router in `src/api/app.py`.
4. Keep permission checks centralized through `with_validation`.