"""Outbound HTTP protections with mocked DNS, sockets and provider responses."""

import json
import socket
import unittest
from unittest.mock import MagicMock, patch

from src.security import outbound_http as http


PUBLIC_DNS = [(socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443))]


class SharedOutboundTests(unittest.TestCase):
    def test_non_public_and_mixed_dns_answers_are_rejected(self):
        for address in ("127.0.0.1", "10.0.0.1", "169.254.169.254", "::1", "fd00::1"):
            answer = [*PUBLIC_DNS, (socket.AF_INET6 if ":" in address else socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", (address, 443))]
            with self.subTest(address=address), patch.object(http.socket, "getaddrinfo", return_value=answer):
                with self.assertRaises(http.UnsafeOutboundUrl):
                    http.validate_outbound_url("https://example.test")

    def test_unsafe_url_shapes_are_rejected(self):
        for value in ("http://example.test", "https://user:pass@example.test", "https://example.test/#fragment", "https://example.test:0", "https://example.test:65536", " https://example.test", "https://example.test/\nunsafe"):
            with self.subTest(value=value), self.assertRaises(http.UnsafeOutboundUrl):
                http.validate_outbound_url(value, resolve=False)

    def test_dns_failure_is_sanitized(self):
        with patch.object(http.socket, "getaddrinfo", side_effect=socket.gaierror("private DNS details")):
            with self.assertRaises(http.UnsafeOutboundUrl) as raised:
                http.validate_outbound_url("https://example.test")
        self.assertNotIn("private DNS", str(raised.exception))

    def test_post_uses_pinned_address_and_json_body(self):
        response = MagicMock(status=201)
        response.read.return_value = b'{"messageId":"accepted"}'
        connection = MagicMock()
        connection.getresponse.return_value = response
        with (patch.object(http.socket, "getaddrinfo", return_value=PUBLIC_DNS) as dns,
              patch.object(http.http.client, "HTTPConnection", return_value=connection) as constructor):
            status, payload = http.post_json("http://example.test/send", allow_http=True,
                headers={"api-key": "test-secret"}, json_payload={"subject": "Hello"})
        dns.assert_called_once()
        constructor.assert_called_once_with("93.184.216.34", 80, timeout=3.0)
        args = connection.request.call_args
        self.assertEqual(args.args, ("POST", "/send"))
        self.assertEqual(json.loads(args.kwargs["body"]), {"subject": "Hello"})
        self.assertEqual(args.kwargs["headers"]["Host"], "example.test")
        self.assertEqual(args.kwargs["headers"]["Content-Type"], "application/json")
        self.assertEqual(status, 201)
        self.assertEqual(payload["messageId"], "accepted")
        connection.close.assert_called_once()

    def test_tls_keeps_original_hostname_for_certificate_validation(self):
        with patch.object(http.socket, "getaddrinfo", return_value=PUBLIC_DNS):
            destination = http.validate_outbound_url("https://example.test")
        context = MagicMock()
        raw_socket = MagicMock()
        with (patch.object(http.ssl, "create_default_context", return_value=context),
              patch.object(http.socket, "create_connection", return_value=raw_socket) as connect):
            connection = http._PinnedHTTPSConnection(destination, "93.184.216.34", 3.0)
            connection.connect()
        self.assertEqual(connect.call_args.args[0], ("93.184.216.34", 443))
        context.wrap_socket.assert_called_once_with(raw_socket, server_hostname="example.test")

    def test_redirect_is_rejected_before_reading_or_forwarding_credentials(self):
        response = MagicMock(status=302)
        connection = MagicMock()
        connection.getresponse.return_value = response
        with (patch.object(http.socket, "getaddrinfo", return_value=PUBLIC_DNS),
              patch.object(http.http.client, "HTTPConnection", return_value=connection)):
            with self.assertRaises(http.OutboundResponseError):
                http.get_json("http://example.test", allow_http=True, headers={"Authorization": "Bearer test"})
        response.read.assert_not_called()
        self.assertEqual(connection.request.call_count, 1)
        connection.close.assert_called_once()

    def test_oversized_or_invalid_response_is_rejected(self):
        for body in (b"x" * 17, b"[]", b"not-json"):
            response = MagicMock(status=200)
            response.read.return_value = body
            connection = MagicMock()
            connection.getresponse.return_value = response
            with self.subTest(body=body), patch.object(http.socket, "getaddrinfo", return_value=PUBLIC_DNS), patch.object(http.http.client, "HTTPConnection", return_value=connection):
                with self.assertRaises(http.OutboundResponseError):
                    http.get_json("http://example.test", allow_http=True, max_response_bytes=16)
            connection.close.assert_called_once()

    def test_oversized_request_is_rejected_before_dns_or_network(self):
        with patch.object(http.socket, "getaddrinfo") as dns:
            with self.assertRaises(http.OutboundResponseError):
                http.post_json("https://example.test", json_payload={"subject": "too large"}, max_request_bytes=1)
        dns.assert_not_called()

    def test_invalid_limits_or_methods_are_rejected(self):
        for kwargs in ({"connect_timeout": 0}, {"read_timeout": float("inf")}, {"max_response_bytes": 0}, {"method": "DELETE"}):
            with self.subTest(kwargs=kwargs), self.assertRaises(ValueError):
                http.request_json("https://example.test", **kwargs)


if __name__ == "__main__":
    unittest.main()
