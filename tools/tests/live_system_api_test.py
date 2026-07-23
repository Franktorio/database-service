"""Live end-to-end coverage for all current system API endpoints.

This module intentionally uses a single requests.Session instance for the
entire flow so cookie-based auth and state transitions are exercised exactly
as a real client would experience them.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import requests

try:
    from dotenv import load_dotenv as _load_dotenv
except ImportError:
    _load_dotenv = None


@dataclass
class StepResult:
    name: str
    ok: bool
    status_code: int | None
    expected_status: int
    details: str


def _load_test_env() -> None:
    """Load config/.env so API_PORT and test vars are available."""
    project_root = Path(__file__).resolve().parents[3]
    env_path = project_root / "config" / ".env"
    if _load_dotenv is not None:
        _load_dotenv(env_path, override=False)
        return

    # Fallback for environments where python-dotenv is unavailable.
    if not env_path.exists():
        return

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and not os.getenv(key):
            os.environ[key] = value


def _read_env_file_vars() -> dict[str, str]:
    project_root = Path(__file__).resolve().parents[2]
    env_path = project_root / "config" / ".env"
    values: dict[str, str] = {}
    if not env_path.exists():
        return values

    for raw_line in env_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("\"'")
        if key:
            values[key] = value
    return values


def _base_url_from_env() -> str:
    file_values = _read_env_file_vars()
    override = (os.getenv("SYSTEM_TEST_BASE_URL") or file_values.get("SYSTEM_TEST_BASE_URL", "")).strip().strip("\"'")
    if override:
        if not (override.startswith("http://") or override.startswith("https://")):
            override = f"http://{override}"
        return override.rstrip("/")

    api_port = (os.getenv("API_PORT") or file_values.get("API_PORT", "8000")).strip() or "8000"
    return f"http://127.0.0.1:{api_port}"


def _auth_headers(super_admin_key: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {super_admin_key}",
        "Content-Type": "application/json",
    }


def run_system_api_live_test() -> dict[str, Any]:
    """Execute all known system API endpoint checks and return a summary report."""
    _load_test_env()

    file_values = _read_env_file_vars()
    super_admin_key = (os.getenv("SYSTEM_TEST_SUPER_ADMIN_KEY") or file_values.get("SYSTEM_TEST_SUPER_ADMIN_KEY", "")).strip()
    if not super_admin_key:
        raise RuntimeError("SYSTEM_TEST_SUPER_ADMIN_KEY is required.")

    base_url = _base_url_from_env()
    headers = _auth_headers(super_admin_key)

    # Dynamic identity values prevent collisions across repeated runs.
    nonce = str(int(time.time()))
    username = f"live_api_user_{nonce}"
    old_password = f"OldP@ss_{nonce}"
    new_password = f"NewP@ss_{nonce}"
    initial_email = f"{username}@example.local"
    updated_email = f"updated_{username}@example.local"

    created_api_token: str | None = None
    created_api_key_hash: str | None = None
    steps: list[StepResult] = []

    def record(
        name: str,
        response: requests.Response | None,
        expected_status: int,
        details: str = "",
    ) -> bool:
        actual_status = None if response is None else response.status_code
        ok = actual_status == expected_status
        steps.append(
            StepResult(
                name=name,
                ok=ok,
                status_code=actual_status,
                expected_status=expected_status,
                details=details,
            )
        )
        return ok

    def safe_json(resp: requests.Response) -> dict[str, Any]:
        try:
            payload = resp.json()
            if isinstance(payload, dict):
                return payload
        except ValueError:
            pass
        return {}

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        # 1) Public health route
        resp = session.get(f"{base_url}/", timeout=20)
        record("GET /", resp, 200, "Root should return greeting payload")

        # 2) Public key-admin root route
        resp = session.get(f"{base_url}/api/db/keys/", timeout=20)
        record("GET /api/db/keys/", resp, 200, "Key admin root should be online")

        # 3) Auth test route (requires API key)
        resp = session.post(f"{base_url}/api-auth-test", headers=headers, timeout=20)
        record("POST /api-auth-test", resp, 200, "Super-admin API key must authenticate")

        # 4) Key listing (requires super admin)
        resp = session.get(f"{base_url}/api/db/keys/list", headers=headers, timeout=20)
        record("GET /api/db/keys/list", resp, 200, "List API keys with super admin")

        # 5) Create API key
        create_api_payload = {
            "permission_level": 1,
            "rate_limit": 321,
            "email": f"{username}+api@example.local",
        }
        resp = session.post(
            f"{base_url}/api/db/keys/create",
            headers=headers,
            json=create_api_payload,
            timeout=20,
        )
        if record("POST /api/db/keys/create", resp, 200, "Create non-super-admin API key"):
            payload = safe_json(resp)
            api_key_object = payload.get("api_key", {})
            if isinstance(api_key_object, dict):
                created_api_token = api_key_object.get("token")
                created_api_key_hash = api_key_object.get("key_hash")

        # 6) Update API key
        if created_api_key_hash:
            update_api_payload = {
                "key_hash": created_api_key_hash,
                "new_permission_level": 2,
                "new_rate_limit": 654,
                "new_email": f"{username}+api-updated@example.local",
            }
            resp = session.post(
                f"{base_url}/api/db/keys/update",
                headers=headers,
                json=update_api_payload,
                timeout=20,
            )
            record("POST /api/db/keys/update", resp, 200, "Update key metadata")
        else:
            steps.append(
                StepResult(
                    name="POST /api/db/keys/update",
                    ok=False,
                    status_code=None,
                    expected_status=200,
                    details="Skipped because API key creation failed.",
                )
            )

        # 7) Create user
        create_user_payload = {
            "username": username,
            "password": old_password,
            "initial_role": "admin",
            "email": initial_email,
            "login_rate_limit": 7,
        }
        resp = session.post(
            f"{base_url}/api/db/users/create",
            headers=headers,
            json=create_user_payload,
            timeout=20,
        )
        record("POST /api/db/users/create", resp, 200, "Create dynamic test user")

        # 8) List users
        resp = session.get(f"{base_url}/api/db/users/list", headers=headers, timeout=20)
        found_user = False
        if resp.status_code == 200:
            users_payload = safe_json(resp).get("users", [])
            if isinstance(users_payload, list):
                found_user = any(isinstance(row, dict) and row.get("username") == username for row in users_payload)
        record("GET /api/db/users/list", resp, 200, f"Created user visible in list={found_user}")

        # 9) Get user by username
        resp = session.get(f"{base_url}/api/db/users/{username}", headers=headers, timeout=20)
        record("GET /api/db/users/{username}", resp, 200, "Fetch dynamic user")

        # 10) Password login should succeed
        resp = session.post(
            f"{base_url}/login-auth-test",
            json={"username": username, "password": old_password},
            timeout=20,
        )
        record("POST /login-auth-test (old password)", resp, 200, "Login with initial password")

        # 11) Cookie auth should succeed on same session
        resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
        record("POST /cookie-auth-test (initial cookie)", resp, 200, "Cookie session should be valid")

        # 12) Update user metadata
        update_user_payload = {
            "username": username,
            "new_email": updated_email,
            "add_role": "auditor",
        }
        resp = session.patch(
            f"{base_url}/api/db/users/update",
            headers=headers,
            json=update_user_payload,
            timeout=20,
        )
        record("PATCH /api/db/users/update", resp, 200, "Update email and roles")

        # 13) Update login rate limit
        resp = session.patch(
            f"{base_url}/api/db/users/login-rate-limit",
            headers=headers,
            json={"username": username, "new_login_rate_limit": 15},
            timeout=20,
        )
        record("PATCH /api/db/users/login-rate-limit", resp, 200, "Update user login rate limit")

        # 14) Update password
        resp = session.patch(
            f"{base_url}/api/db/users/password",
            headers=headers,
            json={"username": username, "new_password": new_password},
            timeout=20,
        )
        record("PATCH /api/db/users/password", resp, 200, "Rotate user password")

        # 15) Old password should fail
        resp = session.post(
            f"{base_url}/login-auth-test",
            json={"username": username, "password": old_password},
            timeout=20,
        )
        record("POST /login-auth-test (old password after rotate)", resp, 401, "Old password must be rejected")

        # 16) Cookie from before password change should fail
        resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
        record("POST /cookie-auth-test (old cookie after rotate)", resp, 401, "Old cookie token should be invalid")

        # 17) New password should succeed
        resp = session.post(
            f"{base_url}/login-auth-test",
            json={"username": username, "password": new_password},
            timeout=20,
        )
        record("POST /login-auth-test (new password)", resp, 200, "New password should authenticate")

        # 18) Cookie auth should succeed again after new login
        resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
        record("POST /cookie-auth-test (new cookie)", resp, 200, "Fresh cookie should authenticate")

        # 19) Delete API key
        if created_api_token:
            resp = session.delete(
                f"{base_url}/api/db/keys/delete",
                headers=headers,
                json={"target_api_key": created_api_token},
                timeout=20,
            )
            record("DELETE /api/db/keys/delete", resp, 200, "Delete created API key")
        else:
            steps.append(
                StepResult(
                    name="DELETE /api/db/keys/delete",
                    ok=False,
                    status_code=None,
                    expected_status=200,
                    details="Skipped because API key creation failed.",
                )
            )

        # 20) Delete user
        resp = session.delete(
            f"{base_url}/api/db/users/delete",
            headers=headers,
            json={"username": username},
            timeout=20,
        )
        record("DELETE /api/db/users/delete", resp, 200, "Delete dynamic user")

    passed = sum(1 for step in steps if step.ok)
    total = len(steps)

    return {
        "ok": passed == total,
        "base_url": base_url,
        "username": username,
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "steps": [step.__dict__ for step in steps],
    }


def _print_report(report: dict[str, Any]) -> None:
    print("=" * 72)
    print("LIVE SYSTEM API TEST REPORT")
    print("=" * 72)
    print(f"Base URL: {report['base_url']}")
    print(f"Dynamic user: {report['username']}")
    print(f"Passed: {report['passed']}/{report['total']} | Failed: {report['failed']}")
    print("-" * 72)

    for step in report["steps"]:
        status = "PASS" if step["ok"] else "FAIL"
        actual = step["status_code"]
        expected = step["expected_status"]
        print(f"[{status}] {step['name']} (expected={expected}, actual={actual})")
        if step["details"]:
            print(f"       {step['details']}")


if __name__ == "__main__":
    result = run_system_api_live_test()
    _print_report(result)
    raise SystemExit(0 if result["ok"] else 1)
