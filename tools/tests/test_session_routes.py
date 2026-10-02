"""Exercise shared session HTTP routes with authorization and persistence mocked."""

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from fastapi.testclient import TestClient

from src.api import app as api
from src.api.config import COOKIE_JWT_INDEX
from src.security import ip_block, sessions, tokens
from src.security.validation.cookie_security import get_current_cookie_data


class SessionRouteTests(unittest.TestCase):
    def setUp(self):
        self.token, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="s" * 43)
        self.identity = SimpleNamespace(username="user@example.test", user_id=42, role="member", roles=["member"],
                                        highest_role_level=0, token_hash=tokens.cookie_session_hash(self.token), rate_limit=120)

        async def authorize():
            return self.identity

        self.previous_overrides = dict(api.app.dependency_overrides)
        api.app.dependency_overrides[get_current_cookie_data] = authorize
        self.ip_patch = patch.object(ip_block, "IP_BLOCKING_ENABLED", False)
        self.ip_patch.start()
        self.client = TestClient(api.app)
        self.client.cookies.set(COOKIE_JWT_INDEX, self.token)

    def tearDown(self):
        self.client.close()
        self.ip_patch.stop()
        api.app.dependency_overrides.clear()
        api.app.dependency_overrides.update(self.previous_overrides)

    def test_refresh_http_route_preserves_app_lifetime_and_session_identity(self):
        with patch.object(sessions, "update_expires_at_for_auth_cookie", new=AsyncMock(return_value=object())):
            response = self.client.post("/me/refresh")
        self.assertEqual(response.status_code, 200, response.text)
        renewed = response.cookies.get(COOKIE_JWT_INDEX)
        self.assertEqual(tokens.cookie_session_hash(renewed), self.identity.token_hash)
        claims = tokens.decode_jwt_token(renewed)
        lifetime = getattr(api, "COOKIE_EXPIRATION_DAYS", None)
        expected_seconds = lifetime * 24 * 60 * 60 if lifetime is not None else tokens.JWT_EXP_MINUTES * 60
        self.assertEqual(claims["exp"] - claims["iat"], expected_seconds)

    def test_me_http_route_reports_signed_expiry(self):
        with (patch.object(api, "get_roles_for_user", new=AsyncMock(return_value=["member"]), create=True),
              patch.object(api, "has_active_membership_for_user", new=AsyncMock(return_value=True), create=True),
              patch.object(api, "must_change_password", new=AsyncMock(return_value=False), create=True)):
            response = self.client.get("/me")
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["username"], self.identity.username)
        self.assertIn("session_expires_at", response.json())
        self.assertIn("session_lifetime_seconds", response.json())

    def test_logout_http_route_revokes_stable_session(self):
        with patch.object(api, "revoke_auth_cookie", new=AsyncMock(return_value=True)) as revoke:
            response = self.client.post("/logout")
        self.assertEqual(response.status_code, 200, response.text)
        revoke.assert_awaited_once_with(self.identity.token_hash)

    def test_unauthenticated_refresh_is_rejected(self):
        async def reject():
            raise HTTPException(status_code=401, detail="Missing session")

        api.app.dependency_overrides[get_current_cookie_data] = reject
        with patch.object(sessions, "update_expires_at_for_auth_cookie", new=AsyncMock()) as update:
            response = self.client.post("/me/refresh")
        self.assertEqual(response.status_code, 401)
        update.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
