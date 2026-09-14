"""Security regressions for outbound HTTP destination validation."""

import socket
import unittest
from unittest.mock import MagicMock, patch

from src.security.outbound_http import UnsafeOutboundUrl, get_json, validate_outbound_url


PUBLIC_RESOLUTION = [
    (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("93.184.216.34", 443)),
]


class OutboundHttpTests(unittest.TestCase):
    def test_https_public_destination_is_accepted(self):
        with patch("src.security.outbound_http.socket.getaddrinfo", return_value=PUBLIC_RESOLUTION):
            destination = validate_outbound_url("https://monitor.example/monitoring/metrics")
        self.assertEqual(destination.hostname, "monitor.example")
        self.assertEqual(destination.addresses, ("93.184.216.34",))

    def test_private_or_mixed_resolution_is_rejected(self):
        mixed = [
            *PUBLIC_RESOLUTION,
            (socket.AF_INET, socket.SOCK_STREAM, socket.IPPROTO_TCP, "", ("127.0.0.1", 443)),
        ]
        with patch("src.security.outbound_http.socket.getaddrinfo", return_value=mixed):
            with self.assertRaises(UnsafeOutboundUrl):
                validate_outbound_url("https://monitor.example/metrics")

    def test_credentials_fragments_and_plain_http_are_rejected(self):
        for value in (
            "http://monitor.example/metrics",
            "https://user:secret@monitor.example/metrics",
            "https://monitor.example/metrics#fragment",
        ):
            with self.subTest(value=value), self.assertRaises(UnsafeOutboundUrl):
                validate_outbound_url(value, resolve=False)

    def test_http_connection_uses_validated_address_not_hostname(self):
        response = MagicMock()
        response.status = 200
        response.read.return_value = b'{"metrics": {}, "recent": {}}'
        connection = MagicMock()
        connection.sock = MagicMock()
        connection.getresponse.return_value = response

        with (
            patch("src.security.outbound_http.socket.getaddrinfo", return_value=PUBLIC_RESOLUTION),
            patch("src.security.outbound_http.http.client.HTTPConnection", return_value=connection) as connection_class,
        ):
            status, payload = get_json(
                "http://monitor.example/metrics",
                allow_http=True,
                query={"refresh": "1"},
            )

        connection_class.assert_called_once_with("93.184.216.34", 80, timeout=3.0)
        connection.request.assert_called_once_with(
            "GET",
            "/metrics?refresh=1",
            headers={"Accept": "application/json", "Host": "monitor.example"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(payload["metrics"], {})


if __name__ == "__main__":
    unittest.main()
