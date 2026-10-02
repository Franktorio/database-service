"""Shared session regressions; database/cache calls are mocked, no live services needed."""

import unittest
from datetime import datetime, timedelta, timezone
from http.cookies import SimpleCookie
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException
from starlette.requests import Request

from src.api.config import COOKIE_JWT_INDEX
from src.models.crud.system import auth_cookie_crud
from src.security import sessions, tokens
from src.security.validation.cookie_security import get_cookie_claims


def request_with_cookie(token):
    return Request({"type": "http", "method": "POST", "path": "/me/refresh",
                    "headers": [(b"cookie", f"{COOKIE_JWT_INDEX}={token}".encode())],
                    "client": ("127.0.0.1", 12345)})


def identity(token):
    return SimpleNamespace(username="user@example.test", user_id=42, role="member",
                           token_hash=tokens.cookie_session_hash(token))


class SharedSessionTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_session_persists_hash_of_stable_id(self):
        user = SimpleNamespace(id=42, username="user@example.test")
        with (patch.object(tokens, "get_user_by_username", new=AsyncMock(return_value=user)),
              patch.object(tokens, "add_auth_cookie", new=AsyncMock()) as add):
            token = await tokens.create_cookie_token(user.username, "member")
        claims = tokens.decode_jwt_token(token)
        self.assertGreaterEqual(len(claims["sid"]), 32)
        self.assertEqual(add.call_args.kwargs["token_hash"], tokens.cookie_session_hash(token))
        renewed, _ = tokens.create_jwt_token(user.username, "member", user.id, session_id=claims["sid"])
        self.assertNotEqual(token, renewed)
        self.assertEqual(tokens.cookie_session_hash(token), tokens.cookie_session_hash(renewed))

    async def test_legacy_cookie_uses_full_original_hash(self):
        token, _ = tokens.create_jwt_token("user@example.test", "member", 42)
        claims = await get_cookie_claims(request_with_cookie(token), token)
        self.assertEqual(claims["token_hash"], tokens.hash_token(token))

    async def test_malformed_session_id_is_rejected(self):
        for sid in ("short", 123, []):
            token, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id=sid)
            with self.subTest(sid=sid), self.assertRaises(HTTPException) as raised:
                await get_cookie_claims(request_with_cookie(token), token)
            self.assertEqual(raised.exception.status_code, 401)

    async def test_expired_signed_cookie_cannot_refresh(self):
        token, _ = tokens.create_jwt_token("user@example.test", "member", 42, expires_minutes=-1, session_id="s" * 43)
        with patch.object(sessions, "update_expires_at_for_auth_cookie", new=AsyncMock()) as update:
            with self.assertRaises(HTTPException) as raised:
                await sessions.refresh_session(request_with_cookie(token), identity(token))
        self.assertEqual(raised.exception.status_code, 401)
        update.assert_not_awaited()

    async def test_refresh_keeps_revocation_identity_and_requested_lifetime(self):
        original, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="s" * 43)
        with patch.object(sessions, "update_expires_at_for_auth_cookie", new=AsyncMock(return_value=object())) as update:
            response = await sessions.refresh_session(request_with_cookie(original), identity(original), expires_minutes=7 * 24 * 60)
        cookies = SimpleCookie()
        cookies.load(response.headers["set-cookie"])
        renewed = cookies[COOKIE_JWT_INDEX].value
        self.assertNotEqual(original, renewed)
        self.assertEqual(tokens.cookie_session_hash(original), tokens.cookie_session_hash(renewed))
        self.assertEqual(update.call_args.args[0], tokens.cookie_session_hash(original))
        self.assertEqual(int(cookies[COOKIE_JWT_INDEX]["max-age"]), 7 * 24 * 60 * 60)
        self.assertEqual(response.headers["cache-control"], "no-store")
        claims = tokens.decode_jwt_token(renewed)
        self.assertEqual(claims["exp"] - claims["iat"], 7 * 24 * 60 * 60)

    async def test_database_rejected_session_cannot_refresh(self):
        token, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="s" * 43)
        with patch.object(sessions, "update_expires_at_for_auth_cookie", new=AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as raised:
                await sessions.refresh_session(request_with_cookie(token), identity(token))
        self.assertEqual(raised.exception.status_code, 401)

    async def test_legacy_refresh_revokes_old_session(self):
        original, _ = tokens.create_jwt_token("user@example.test", "member", 42)
        replacement, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="n" * 43)
        with (patch.object(sessions, "create_cookie_token", new=AsyncMock(return_value=replacement)),
              patch.object(sessions, "revoke_auth_cookie", new=AsyncMock(return_value=True)) as revoke):
            response = await sessions.refresh_session(request_with_cookie(original), identity(original))
        revoke.assert_awaited_once_with(tokens.hash_token(original))
        self.assertIn(replacement, response.headers["set-cookie"])

    async def test_failed_legacy_upgrade_revokes_replacement(self):
        original, _ = tokens.create_jwt_token("user@example.test", "member", 42)
        replacement, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="n" * 43)
        with (patch.object(sessions, "create_cookie_token", new=AsyncMock(return_value=replacement)),
              patch.object(sessions, "revoke_auth_cookie", new=AsyncMock(side_effect=[False, True])) as revoke):
            with self.assertRaises(HTTPException) as raised:
                await sessions.refresh_session(request_with_cookie(original), identity(original))
        self.assertEqual(raised.exception.status_code, 401)
        self.assertEqual(revoke.await_args_list[1].args[0], tokens.cookie_session_hash(replacement))

    async def test_mismatched_authorized_identity_is_rejected(self):
        token, _ = tokens.create_jwt_token("user@example.test", "member", 42, session_id="s" * 43)
        user = identity(token)
        user.token_hash = "truncated-or-wrong"
        with self.assertRaises(HTTPException) as raised:
            await sessions.refresh_session(request_with_cookie(token), user)
        self.assertEqual(raised.exception.status_code, 401)

    async def test_metadata_uses_signed_expiry(self):
        token, _ = tokens.create_jwt_token("user@example.test", "member", 42)
        metadata = sessions.session_metadata(request_with_cookie(token))
        self.assertEqual(int(datetime.fromisoformat(metadata["session_expires_at"]).timestamp()), tokens.decode_jwt_token(token)["exp"])

    async def test_database_expiry_update_rejects_inactive_rows_and_invalidates_cache(self):
        row = SimpleNamespace(expires_at=datetime.now(timezone.utc) + timedelta(minutes=5))
        result = SimpleNamespace(scalar_one_or_none=lambda: row)
        session = SimpleNamespace(execute=AsyncMock(return_value=result), commit=AsyncMock(), refresh=AsyncMock())
        expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        with patch.object(auth_cookie_crud, "invalidate_cookie_permission_cache", new=AsyncMock()) as invalidate:
            renewed = await auth_cookie_crud.update_expires_at_for_auth_cookie("full-hash", expires_at, session=session)
        self.assertIs(renewed, row)
        self.assertEqual(row.expires_at, expires_at)
        statement = str(session.execute.call_args.args[0])
        self.assertIn("revoked IS false", statement)
        self.assertIn("expires_at >", statement)
        invalidate.assert_awaited_once_with("full-hash")


if __name__ == "__main__":
    unittest.main()
