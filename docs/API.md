# API Reference

The API service currently exposes two layers:

1. Root and auth checks in `src/api/app.py`.
2. Super-admin DB administration in `src/api/system/`.

## Current Admin Surface

- `GET /` returns a service greeting.
- `POST /api-auth-test` validates the supplied API key and echoes the resolved permissions.
- `POST /login-auth-test` validates username/password and issues an auth cookie.
- `POST /cookie-auth-test` validates auth cookie access.
- `GET /api/db/keys` returns a simple health message for the API-key admin surface.
- `GET /api/db/keys/list` lists stored API keys.
- `POST /api/db/keys/create` creates a new API key.
- `POST /api/db/keys/update` updates an API key by `key_hash`.
- `DELETE /api/db/keys/delete` deletes an API key by hashing the supplied token in the request body.
- `POST /api/db/users/create` creates a new user account.
- `GET /api/db/users/list` lists users.
- `GET /api/db/users/{username}` fetches one user.
- `PATCH /api/db/users/update` updates user email/roles.
- `PATCH /api/db/users/password` updates user password metadata.
- `PATCH /api/db/users/login-rate-limit` updates per-user login rate limit.
- `DELETE /api/db/users/delete` deletes one user by username.

## Authorization

All API-key admin endpoints require `SUPER_ADMIN_LEVEL` access. The bootstrap SUPER_ADMIN key is intended to be created from `scripts/generate_api_key.py`.

## Python Example Usage

The examples below use the `requests` package and send JSON request bodies.

```python
import requests

BASE_URL = "http://127.0.0.1:8000"
ADMIN_API_KEY = "your-super-admin-api-key"


def post_json(path: str, payload: dict):
	response = requests.post(f"{BASE_URL}{path}", json=payload, timeout=10)
	print(path, response.status_code)
	print(response.json())
	return response


def patch_json(path: str, payload: dict):
	response = requests.patch(f"{BASE_URL}{path}", json=payload, timeout=10)
	print(path, response.status_code)
	print(response.json())
	return response


def delete_json(path: str, payload: dict):
	response = requests.delete(f"{BASE_URL}{path}", json=payload, timeout=10)
	print(path, response.status_code)
	print(response.json())
	return response
```

### Create User

```python
payload = {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
	"password": "change-me-please",
	"role": "admin",
	"email": "alice@example.com",
	"login_rate_limit": 12,
}

post_json("/api/db/users/create", payload)
```

### Update User Roles (Set / Add / Remove)

```python
# Set full role list
patch_json("/api/db/users/update", {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
	"set_roles": ["admin", "editor"],
})

# Add one role
patch_json("/api/db/users/update", {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
	"add_role": "auditor",
})

# Remove one role
patch_json("/api/db/users/update", {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
	"remove_role": "editor",
})

# Update email and roles together
patch_json("/api/db/users/update", {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
	"new_email": "alice+ops@example.com",
	"add_role": "support",
})
```

### List / Fetch / Delete Users

```python
# List users
response = requests.get(
	f"{BASE_URL}/api/db/users/list",
	params={"api_key": ADMIN_API_KEY},
	timeout=10,
)
print(response.status_code)
print(response.json())

# Fetch one user
response = requests.get(
	f"{BASE_URL}/api/db/users/alice",
	params={"api_key": ADMIN_API_KEY},
	timeout=10,
)
print(response.status_code)
print(response.json())

# Delete user
delete_json("/api/db/users/delete", {
	"api_key": ADMIN_API_KEY,
	"username": "alice",
})
```

### API Key Admin Examples

```python
# Create API key
post_json("/api/db/keys/create", {
	"api_key": ADMIN_API_KEY,
	"permission_level": 1,
	"rate_limit": 300,
	"email": "service@example.com",
})

# Update API key by key_hash
post_json("/api/db/keys/update", {
	"api_key": ADMIN_API_KEY,
	"key_hash": "your-target-key-hash",
	"new_permission_level": 2,
	"new_rate_limit": 500,
	"new_email": "service-updated@example.com",
})

# Delete API key by raw token in request
delete_json("/api/db/keys/delete", {
	"api_key": ADMIN_API_KEY,
	"target_api_key": "raw-token-to-delete",
})
```

## Expansion Pattern

When adding a new API surface:

1. Create a new router package under `src/api/system/`.
2. Define request models close to the routes that use them.
3. Register the router in `src/api/app.py`.
4. Keep permission checks centralized through `with_validation`.