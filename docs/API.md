# API Reference

This service exposes a small administrative API plus two authentication test flows.

## Global Behavior

- Most routes are wrapped with IP blocking.
- API-key-protected routes use `api_authentication`.
- Cookie-protected routes use `cookie_authentication`.
- `GET` admin endpoints expect `api_key` as a query parameter.
- Non-`GET` admin endpoints expect `api_key` in the JSON body.

## Public/Test Endpoints

### `GET /`

Returns a simple greeting payload.

### `POST /api-auth-test`

Validates an API key and returns resolved permission metadata.

Request body:

```json
{
  "api_key": "your-api-key"
}
```

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

All endpoints in this section require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/keys/`

Simple availability message for the API-key administration surface.

### `GET /api/db/keys/list`

Lists stored API keys.

Query params:

- `api_key`: SUPER_ADMIN bootstrap or existing SUPER_ADMIN key.

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
  "api_key": "super-admin-api-key",
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
  "api_key": "super-admin-api-key",
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
  "api_key": "super-admin-api-key",
  "target_api_key": "raw-token-to-delete"
}
```

## User Administration

Base prefix: `/api/db/users`

All endpoints in this section require `SUPER_ADMIN_LEVEL`.

### `GET /api/db/users/list`

Lists all users.

Query params:

- `api_key`: SUPER_ADMIN key.

### `GET /api/db/users/{username}`

Fetches a single user by username.

Query params:

- `api_key`: SUPER_ADMIN key.

### `POST /api/db/users/create`

Creates a user and hashes the submitted password.

Request body:

```json
{
  "api_key": "super-admin-api-key",
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
  "api_key": "super-admin-api-key",
  "username": "alice",
  "set_roles": ["admin", "editor"]
}
```

```json
{
  "api_key": "super-admin-api-key",
  "username": "alice",
  "add_role": "auditor"
}
```

```json
{
  "api_key": "super-admin-api-key",
  "username": "alice",
  "remove_role": "editor"
}
```

### `PATCH /api/db/users/password`

Replaces password hash metadata for a user.

Request body:

```json
{
  "api_key": "super-admin-api-key",
  "username": "alice",
  "new_password": "new-secret"
}
```

### `PATCH /api/db/users/login-rate-limit`

Updates the per-user password-login rate limit.

Request body:

```json
{
  "api_key": "super-admin-api-key",
  "username": "alice",
  "new_login_rate_limit": 20
}
```

### `DELETE /api/db/users/delete`

Deletes a user by username.

Request body:

```json
{
  "api_key": "super-admin-api-key",
  "username": "alice"
}
```

## Security Notes

- API keys are stored as hashes, not raw tokens.
- Cookie tokens are also stored by hash for revocation checks.
- `SUPER_ADMIN` keys cannot be created through the HTTP API.
- GET endpoints use query params for `api_key`, which is convenient but less ideal from a secret-handling perspective than a header.

## Known Gaps

- API-key and cookie ratelimits are process-local.
- Secret-bearing GET admin endpoints still accept `api_key` via query parameters instead of an authorization header.
- Persistent logging occurs on auth success and failure paths, which adds DB dependency to control-plane traffic.
