# API Reference

This service exposes a small administrative API plus optional authentication test flows.

## Global Behavior

- Most routes are wrapped with IP blocking.
- API-key-protected routes use `api_authentication`.
- Cookie-protected routes use `cookie_authentication`.
- API-key-protected endpoints require `Authorization: Bearer <api_key>`.
- Rate-limit counters are stored in Redis; protected auth routes return `503` if Redis is unavailable.

IP blocking defaults (app-level):

- `IP_BLOCKING_ENABLED='true'`
- `IP_BLOCKING_THRESHOLD='200'`
- `IP_BLOCKING_TIME_WINDOW='15'`
- `IP_BLOCKING_DURATION='1800'`
- Default behavior: 200 requests within 15 seconds blocks that IP for 30 minutes.

Authorization format for API-key-protected endpoints:

```http
Authorization: Bearer your-api-key
```

## Public/Test Endpoints

Auth/test helper endpoints below are only mounted when `API_EXPOSE_TEST_ENDPOINTS=true`.

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

All API-key administration endpoints require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/keys`

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

### `POST /api/db/keys`

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
    "permission_level": 1,
    "permission_name": "EDIT",
    "rate_limit": 300,
    "email": "service@example.com"
  }
}
```

### `PATCH /api/db/keys/{key_hash}`

Updates an API key by path `key_hash`.

Request body:

```json
{
  "new_permission_level": 2,
  "new_rate_limit": 500,
  "new_email": "service-updated@example.com"
}
```

### `DELETE /api/db/keys/{key_hash}`

Deletes an API key by path `key_hash`.

## User Administration

Base prefix: `/api/db/users`

All endpoints in this section require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/users`

Lists all users.

### `GET /api/db/users/{username}`

Fetches a single user by username.

### `POST /api/db/users`

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

### `PATCH /api/db/users/{username}`

Updates user email and/or roles.

Request body examples:

```json
{
  "set_roles": ["admin", "editor"]
}
```

```json
{
  "add_role": "auditor"
}
```

```json
{
  "remove_role": "editor"
}
```

### `PATCH /api/db/users/{username}/password`

Replaces password hash metadata for a user.

Request body:

```json
{
  "new_password": "new-secret"
}
```

### `PATCH /api/db/users/{username}/login-rate-limit`

Updates the per-user password-login rate limit.

Request body:

```json
{
  "new_login_rate_limit": 20
}
```

### `DELETE /api/db/users/{username}`

Deletes a user by username path parameter.

## Security Notes

- API keys are stored as hashes, not raw tokens.
- Cookie tokens are also stored by hash for revocation checks.
- `SUPER_ADMIN` keys cannot be created through the HTTP API.
- API-key auth uses `Authorization: Bearer <api_key>` to avoid query/body secret transport.

## Known Gaps

- IP block duration and Redis key TTL are independently configurable; a TTL shorter than block duration can clear a block earlier than intended.
- API and auth paths still mix control logic with request serving, so startup and maintenance behavior should be treated as part of the app runtime.

## Live Test Notes

The live system test suite is implemented under:

- `tools/tests/live_system_api_test.py`

Environment variables used by the suite:

- `SYSTEM_TEST_SUPER_ADMIN_KEY` (required)
- `API_PORT` (used to build base URL from `.env`)
- `SYSTEM_TEST_BASE_URL` (optional override; if set, this takes precedence)
