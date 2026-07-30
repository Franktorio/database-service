"""Live end-to-end coverage for all current system API endpoints."""

from __future__ import annotations

import os
import sys
import time
import json
from pathlib import Path
from typing import Any

import requests

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.loader import API_PORT


def _base_url() -> str:
    override = os.getenv("SYSTEM_TEST_BASE_URL", "").strip().strip("\"'")
    if override:
        if not (override.startswith("http://") or override.startswith("https://")):
            override = f"http://{override}"
        return override.rstrip("/")
    return f"http://127.0.0.1:{API_PORT}"


def _super_admin_headers() -> dict[str, str]:
    key = os.getenv("SYSTEM_TEST_SUPER_ADMIN_KEY", "").strip()
    if not key:
        raise RuntimeError("SYSTEM_TEST_SUPER_ADMIN_KEY is required.")
    return {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    
def _pretty_print_json(data: Any) -> None:

    print(json.dumps(data, indent=4, sort_keys=True))


def _record(
    steps: list[dict[str, Any]],
    name: str,
    response: requests.Response | None,
    expected_status: int,
    details: str = "",
) -> bool:
    actual_status = None if response is None else response.status_code
    ok = actual_status == expected_status
    steps.append(
        {
            "name": name,
            "ok": ok,
            "status_code": actual_status,
            "expected_status": expected_status,
            "details": details,
        }
    )
    return ok


def _step_get_root(session: requests.Session, base_url: str, steps: list[dict[str, Any]]) -> None:
    resp = session.get(f"{base_url}/", timeout=20)
    _record(steps, "GET /", resp, 200, "Root should return greeting payload")


def _step_get_key_admin_root(session: requests.Session, base_url: str, steps: list[dict[str, Any]]) -> None:
    resp = session.get(f"{base_url}/api/db/keys", timeout=20)
    _record(steps, "GET /api/db/keys", resp, 401, "Collection endpoint requires API key")


def _step_api_auth_test(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.post(f"{base_url}/api-auth-test", headers=headers, timeout=20)
    _record(steps, "POST /api-auth-test", resp, 200, "Super-admin API key must authenticate")


def _step_list_api_keys(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.get(f"{base_url}/api/db/keys", headers=headers, timeout=20)
    _record(steps, "GET /api/db/keys", resp, 200, "List API keys with super admin")


def _step_create_api_key(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.post(
        f"{base_url}/api/db/keys",
        headers=headers,
        json={"permission_level": 1, "rate_limit": 321, "email": state["api_email"]},
        timeout=20,
    )
    created = _record(steps, "POST /api/db/keys", resp, 200, "Create non-super-admin API key")
    if not created:
        return

    payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    api_key = payload.get("api_key", {}) if isinstance(payload, dict) else {}
    token = api_key.get("token") if isinstance(api_key, dict) else None
    key_id = api_key.get("id") if isinstance(api_key, dict) else None
    if isinstance(token, str) and token:
        state["created_api_token"] = token
    if isinstance(key_id, int):
        state["created_api_key_id"] = key_id


def _step_update_api_key(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    key_id = state.get("created_api_key_id")
    if key_id is None:
        steps.append(
            {
                "name": "PATCH /api/db/keys/{key_id}",
                "ok": False,
                "status_code": None,
                "expected_status": 200,
                "details": "Skipped because created API key id is unavailable.",
            }
        )
        return

    resp = session.patch(
        f"{base_url}/api/db/keys/{key_id}",
        headers=headers,
        json={
            "new_permission_level": 2,
            "new_rate_limit": 30,
            "new_email": state["api_updated_email"],
        },
        timeout=20,
    )
    _record(steps, "PATCH /api/db/keys/{key_id}", resp, 200, "Update key metadata")


def _step_rate_limit_test(
    session: requests.Session,
    base_url: str,
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    token = state.get("created_api_token")
    if not token:
        steps.append(
            {
                "name": "RATE LIMIT /api-auth-test",
                "ok": False,
                "status_code": None,
                "expected_status": 429,
                "details": "Skipped because created API key token is unavailable.",
            }
        )
        return

    limited_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    last_status = None
    for i in range(100):
        resp = session.post(f"{base_url}/api-auth-test", headers=limited_headers, timeout=20)
        last_status = resp.status_code

        if resp.status_code == 429:
            _record(
                steps,
                "RATE LIMIT /api-auth-test",
                resp,
                429,
                f"Received 429 at request {i + 1} while testing 100 requests.",
            )
            return

        if resp.status_code != 200:
            steps.append(
                {
                    "name": "RATE LIMIT /api-auth-test",
                    "ok": False,
                    "status_code": resp.status_code,
                    "expected_status": 429,
                    "details": f"Unexpected status {resp.status_code} at request {i + 1}.",
                }
            )
            return

    steps.append(
        {
            "name": "RATE LIMIT /api-auth-test",
            "ok": False,
            "status_code": last_status,
            "expected_status": 429,
            "details": "No 429 returned after 100 requests; rate-limit test failed.",
        }
    )


def _step_create_user(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.post(
        f"{base_url}/api/db/users",
        headers=headers,
        json={
            "username": state["username"],
            "password": state["old_password"],
            "initial_role": "admin",
            "email": state["initial_email"],
            "login_rate_limit": 7,
        },
        timeout=20,
    )
    _record(steps, "POST /api/db/users", resp, 200, "Create dynamic test user")


def _step_list_users(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.get(f"{base_url}/api/db/users", headers=headers, timeout=20)
    found_user = False
    if resp.status_code == 200:
        payload = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
        users = payload.get("users", []) if isinstance(payload, dict) else []
        if isinstance(users, list):
            found_user = any(isinstance(row, dict) and row.get("username") == state["username"] for row in users)
    _record(steps, "GET /api/db/users", resp, 200, f"Created user visible in list={found_user}")


def _step_get_user(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.get(f"{base_url}/api/db/users/{state['username']}", headers=headers, timeout=20)
    _record(steps, "GET /api/db/users/{username}", resp, 200, "Fetch dynamic user")


def _step_login_old_password(session: requests.Session, base_url: str, state: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    resp = session.post(
        f"{base_url}/login-auth-test",
        json={"username": state["username"], "password": state["old_password"]},
        timeout=20,
    )
    _record(steps, "POST /login-auth-test (old password)", resp, 200, "Login with initial password")


def _step_cookie_auth_initial(session: requests.Session, base_url: str, steps: list[dict[str, Any]]) -> None:
    resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
    _record(steps, "POST /cookie-auth-test (initial cookie)", resp, 200, "Cookie session should be valid")


def _step_update_user(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.patch(
        f"{base_url}/api/db/users/{state['username']}",
        headers=headers,
        json={"new_email": state["updated_email"], "add_role": "auditor"},
        timeout=20,
    )
    _record(steps, "PATCH /api/db/users/{username}", resp, 200, "Update email and roles")


def _step_update_user_login_rate_limit(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.patch(
        f"{base_url}/api/db/users/{state['username']}/login-rate-limit",
        headers=headers,
        json={"new_login_rate_limit": 15},
        timeout=20,
    )
    _record(steps, "PATCH /api/db/users/{username}/login-rate-limit", resp, 200, "Update user login rate limit")


def _step_update_user_password(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.patch(
        f"{base_url}/api/db/users/{state['username']}/password",
        headers=headers,
        json={"new_password": state["new_password"]},
        timeout=20,
    )
    _record(steps, "PATCH /api/db/users/{username}/password", resp, 200, "Rotate user password")


def _step_login_old_password_rejected(
    session: requests.Session,
    base_url: str,
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.post(
        f"{base_url}/login-auth-test",
        json={"username": state["username"], "password": state["old_password"]},
        timeout=20,
    )
    _record(steps, "POST /login-auth-test (old password after rotate)", resp, 401, "Old password must be rejected")


def _step_cookie_old_rejected(session: requests.Session, base_url: str, steps: list[dict[str, Any]]) -> None:
    resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
    _record(steps, "POST /cookie-auth-test (old cookie after rotate)", resp, 401, "Old cookie token should be invalid")


def _step_login_new_password(session: requests.Session, base_url: str, state: dict[str, Any], steps: list[dict[str, Any]]) -> None:
    resp = session.post(
        f"{base_url}/login-auth-test",
        json={"username": state["username"], "password": state["new_password"]},
        timeout=20,
    )
    _record(steps, "POST /login-auth-test (new password)", resp, 200, "New password should authenticate")


def _step_cookie_auth_new(session: requests.Session, base_url: str, steps: list[dict[str, Any]]) -> None:
    resp = session.post(f"{base_url}/cookie-auth-test", timeout=20)
    _record(steps, "POST /cookie-auth-test (new cookie)", resp, 200, "Fresh cookie should authenticate")


def _step_delete_api_key(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    token = state.get("created_api_token")
    key_id = state.get("created_api_key_id")
    if not token or key_id is None:
        steps.append(
            {
                "name": "DELETE /api/db/keys/{key_id}",
                "ok": False,
                "status_code": None,
                "expected_status": 200,
                "details": "Skipped because created API key token/id is unavailable.",
            }
        )
        return

    resp = session.delete(
        f"{base_url}/api/db/keys/{key_id}",
        headers=headers,
        timeout=20,
    )
    _record(steps, "DELETE /api/db/keys/{key_id}", resp, 200, "Delete created API key")


def _step_delete_user(
    session: requests.Session,
    base_url: str,
    headers: dict[str, str],
    state: dict[str, Any],
    steps: list[dict[str, Any]],
) -> None:
    resp = session.delete(
        f"{base_url}/api/db/users/{state['username']}",
        headers=headers,
        timeout=20,
    )
    _record(steps, "DELETE /api/db/users/{username}", resp, 200, "Delete dynamic user")


def run_system_api_live_test() -> dict[str, Any]:
    base_url = _base_url()
    headers = _super_admin_headers()

    nonce = str(int(time.time()))
    username = f"live_api_user_{nonce}"
    state: dict[str, Any] = {
        "username": username,
        "old_password": f"OldP@ss_{nonce}",
        "new_password": f"NewP@ss_{nonce}",
        "initial_email": f"{username}@example.local",
        "updated_email": f"updated_{username}@example.local",
        "api_email": f"{username}+api@example.local",
        "api_updated_email": f"{username}+api-updated@example.local",
        "created_api_token": None,
        "created_api_key_id": None,
    }

    steps: list[dict[str, Any]] = []

    with requests.Session() as session:
        session.headers.update({"Accept": "application/json"})

        _step_get_root(session, base_url, steps)
        _step_get_key_admin_root(session, base_url, steps)
        _step_api_auth_test(session, base_url, headers, steps)
        _step_list_api_keys(session, base_url, headers, steps)
        _step_create_api_key(session, base_url, headers, state, steps)
        _step_update_api_key(session, base_url, headers, state, steps)
        _step_rate_limit_test(session, base_url, state, steps)

        _step_create_user(session, base_url, headers, state, steps)
        _step_list_users(session, base_url, headers, state, steps)
        _step_get_user(session, base_url, headers, state, steps)
        _step_login_old_password(session, base_url, state, steps)
        _step_cookie_auth_initial(session, base_url, steps)

        _step_update_user(session, base_url, headers, state, steps)
        _step_update_user_login_rate_limit(session, base_url, headers, state, steps)
        _step_update_user_password(session, base_url, headers, state, steps)
        _step_login_old_password_rejected(session, base_url, state, steps)
        _step_cookie_old_rejected(session, base_url, steps)
        _step_login_new_password(session, base_url, state, steps)
        _step_cookie_auth_new(session, base_url, steps)

        _step_delete_api_key(session, base_url, headers, state, steps)
        _step_delete_user(session, base_url, headers, state, steps)

    passed = sum(1 for step in steps if step["ok"])
    total = len(steps)
    return {
        "ok": passed == total,
        "base_url": base_url,
        "username": username,
        "passed": passed,
        "failed": total - passed,
        "total": total,
        "steps": steps,
    }

def get_metrics() -> dict[str, Any]:
    """Get the current monitoring metrics from the API service."""
    base_url = _base_url()
    try:
        response = requests.get(f"{base_url}/health", timeout=10)
        if response.status_code == 200:
            return response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        else:
            return {"error": f"Unexpected status code {response.status_code}"}
    except requests.RequestException as e:
        return {"error": str(e)}

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
    
    metrcics = get_metrics()
    print("-" * 72)
    print("API SERVICE METRICS")
    _pretty_print_json(metrcics)


if __name__ == "__main__":
    result = run_system_api_live_test()
    _print_report(result)
    raise SystemExit(0 if result["ok"] else 1)
