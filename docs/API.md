# API Reference

This service exposes a small administrative API plus two authentication test flows.

## Global Behavior

- Most routes are wrapped with IP blocking.
- API-key-protected routes use `api_authentication`.
- Cookie-protected routes use `cookie_authentication`.
- API-key-protected endpoints require `Authorization: Bearer <api_key>`.

Authorization format for API-key-protected endpoints:

```http
Authorization: Bearer your-api-key
```

## Public/Test Endpoints

### `GET /`

Returns a simple greeting payload.

### `POST /api-auth-test`

Validates an API key and returns resolved permission metadata.

### `POST /login-auth-test`

Validates username/password and returns a cookie-authenticated session cookie.

Request body:

```json
{
  "username": "alice",
  "password": "change-me"
}
```

### `POST /cookie-auth-test`

Requires the configured auth cookie and returns a success payload when the cookie is valid.

## API Key Administration

Base prefix: `/api/db/keys`

Endpoints in this section have mixed authorization:

- `GET /api/db/keys/` is public (IP block middleware still applies).
- The remaining API-key administration endpoints require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/keys/`

Simple availability message for the API-key administration surface.

### `GET /api/db/keys/list`

Lists stored API keys.

Response shape:

```json
{
  "api_keys": [
    {
      "id": 1,
      "key_hash": "...",
      "permission_level": 1,
      "permission_name": "EDIT",
      "rate_limit": 300,
      "email": "service@example.com",
      "created_at": "...",
      "last_updated_at": "..."
    }
  ]
}
```

### `POST /api/db/keys/create`

Creates a non-SUPER_ADMIN API key.

Request body:

```json
{
  "permission_level": 1,
  "rate_limit": 300,
  "email": "service@example.com"
}
```

Response includes the raw token once:

```json
{
  "message": "API key created successfully.",
  "api_key": {
    "token": "raw-token",
    "key_hash": "hashed-token",
    "permission_level": 1,
    "permission_name": "EDIT",
    "rate_limit": 300,
    "email": "service@example.com"
  }
}
```

### `POST /api/db/keys/update`

Updates an API key by `key_hash`.

Request body:

```json
{
  "key_hash": "target-key-hash",
  "new_permission_level": 2,
  "new_rate_limit": 500,
  "new_email": "service-updated@example.com"
}
```

### `DELETE /api/db/keys/delete`

Deletes an API key by hashing the supplied raw target token.

Request body:

```json
{
  "target_api_key": "raw-token-to-delete"
}
```

## User Administration

Base prefix: `/api/db/users`

All endpoints in this section require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/users/list`

Lists all users.

### `GET /api/db/users/{username}`

Fetches a single user by username.

### `POST /api/db/users/create`

Creates a user and hashes the submitted password.

Request body:

```json
{
  "username": "alice",
  "password": "change-me-please",
  "initial_role": "admin",
  "email": "alice@example.com",
  "login_rate_limit": 12
}
```

### `PATCH /api/db/users/update`

Updates user email and/or roles.

Request body examples:

```json
{
  "username": "alice",
  "set_roles": ["admin", "editor"]
}
```

```json
{
  "username": "alice",
  "add_role": "auditor"
}
```

```json
{
  "username": "alice",
  "remove_role": "editor"
}
```

### `PATCH /api/db/users/password`

Replaces password hash metadata for a user.

Request body:

```json
{
  "username": "alice",
  "new_password": "new-secret"
}
```

### `PATCH /api/db/users/login-rate-limit`

Updates the per-user password-login rate limit.

Request body:

```json
{
  "username": "alice",
  "new_login_rate_limit": 20
}
```

### `DELETE /api/db/users/delete`

Deletes a user by username.

Request body:

```json
{
  "username": "alice"
}
```

## Security Notes

- API keys are stored as hashes, not raw tokens.
- Cookie tokens are also stored by hash for revocation checks.
- `SUPER_ADMIN` keys cannot be created through the HTTP API.
- API-key auth uses `Authorization: Bearer <api_key>` to avoid query/body secret transport.

## Known Gaps

- API-key and cookie ratelimits are process-local.
- Persistent logging occurs on auth success and failure paths, which adds DB dependency to control-plane traffic.

## Live Test Notes

The live system test suite is implemented under:

- `tools/tests/live_system_api_test.py`

Environment variables used by the suite:

- `SYSTEM_TEST_SUPER_ADMIN_KEY` (required)
- `API_PORT` (used to build base URL from `.env`)
- `SYSTEM_TEST_BASE_URL` (optional override; if set, this takes precedence)
