"""Brevo transport and template contracts without sending real messages."""

import unittest
from unittest.mock import AsyncMock, patch

from src.security.outbound_http import OutboundResponseError
from src.services.system import emailing


class SharedEmailTests(unittest.IsolatedAsyncioTestCase):
    async def test_brevo_payload_and_security_timeouts(self):
        with (patch.object(emailing, "BREVO_API_KEY", "test-secret"),
              patch.object(emailing, "BREVO_FROM_EMAIL", "sender@example.test"),
              patch.object(emailing, "post_json", return_value=(201, {"messageId": "message-123"})) as post):
            message = await emailing.send_email(to_email="user@example.test", to_name="User", subject="Hello",
                html_content="<p>Hello</p>", text_content="Hello", tags=["test"], attachments=[{"name": "test.txt", "content": "SGVsbG8="}])
        self.assertEqual(message, "message-123")
        self.assertEqual(post.call_args.args[0], "https://api.brevo.com/v3/smtp/email")
        args = post.call_args.kwargs
        self.assertEqual(args["headers"]["api-key"], "test-secret")
        self.assertEqual(args["json_payload"]["textContent"], "Hello")
        self.assertEqual(args["json_payload"]["attachment"][0]["name"], "test.txt")
        self.assertEqual(args["connect_timeout"], emailing.BREVO_REQUEST_TIMEOUT_SECONDS)
        self.assertEqual(args["read_timeout"], emailing.BREVO_REQUEST_TIMEOUT_SECONDS)

    async def test_missing_configuration_never_attempts_delivery(self):
        with (patch.object(emailing, "BREVO_API_KEY", ""), patch.object(emailing, "post_json") as post):
            with self.assertRaises(emailing.EmailDeliveryError):
                await emailing.send_email(to_email="user@example.test", subject="Hello", html_content="Hello")
        post.assert_not_called()

    async def test_bad_provider_responses_are_rejected_without_sensitive_details(self):
        responses = [(401, {"message": "test-secret private-message"}), (201, {}), (201, {"messageId": 123})]
        for response in responses:
            with self.subTest(response=response), patch.object(emailing, "BREVO_API_KEY", "test-secret"), patch.object(emailing, "BREVO_FROM_EMAIL", "sender@example.test"), patch.object(emailing, "post_json", return_value=response):
                with self.assertRaises(emailing.EmailDeliveryError) as raised:
                    await emailing.send_email(to_email="user@example.test", subject="Hello", html_content="private-message")
                self.assertNotIn("test-secret", str(raised.exception))
                self.assertNotIn("private-message", str(raised.exception))

    async def test_transport_failure_is_reported_safely(self):
        with (patch.object(emailing, "BREVO_API_KEY", "test-secret"), patch.object(emailing, "BREVO_FROM_EMAIL", "sender@example.test"),
              patch.object(emailing, "post_json", side_effect=OutboundResponseError("sensitive transport details"))):
            with self.assertRaises(emailing.EmailDeliveryError) as raised:
                await emailing.send_email(to_email="user@example.test", subject="Hello", html_content="Hello")
        self.assertNotIn("sensitive", str(raised.exception))

    async def test_brand_and_user_content_are_escaped(self):
        with patch.object(emailing, "BREVO_FROM_NAME", '<img src="brand">'):
            html = emailing._action_email_html(heading="<script>", greeting_name="<user>", body="<body>",
                action_label="<action>", action_url='https://example.test/?value="quoted"', expiry_text="<expiry>")
        self.assertIn("&lt;img", html)
        self.assertNotIn("<script>", html)
        self.assertIn("&quot;quoted&quot;", html)

    async def test_account_access_helpers_keep_existing_links_and_tags(self):
        with (patch.object(emailing, "PUBLIC_APP_URL", "https://example.test"),
              patch.object(emailing, "BREVO_FROM_NAME", "Test Brand"),
              patch.object(emailing, "send_email", new=AsyncMock(return_value="message")) as send):
            await emailing.send_verification_email(to_email="user@example.test", to_name="User", onboarding_path="/users/login/42?temporary=token")
            self.assertIn("https://example.test/users/login/42?temporary=token", send.call_args.kwargs["html_content"])
            self.assertIn("Test Brand", send.call_args.kwargs["subject"])
            self.assertEqual(send.call_args.kwargs["tags"], ["account-verification"])
            await emailing.send_password_reset_email(to_email="user@example.test", to_name="User", reset_path="/users/login/42?flow=reset")
            self.assertEqual(send.call_args.kwargs["tags"], ["password-reset"])


if __name__ == "__main__":
    unittest.main()
