"""SSRF-resistant helpers for small server-side JSON requests.

The destination is parsed and resolved once. The HTTP connection is then made
to that exact validated address while retaining the original Host header and,
for TLS, the original hostname for certificate validation and SNI. This avoids
the DNS-rebinding gap created by validating a hostname and letting an HTTP
client resolve it again later.
"""

from __future__ import annotations

import http.client
import ipaddress
import json
import socket
import ssl
from dataclasses import dataclass
from typing import Mapping
from urllib.parse import SplitResult, urlencode, urlsplit, urlunsplit


MAX_JSON_RESPONSE_BYTES = 2 * 1024 * 1024


class UnsafeOutboundUrl(ValueError):
    """Raised when an outbound destination is malformed or unsafe."""


class OutboundResponseError(RuntimeError):
    """Raised when an outbound response cannot be handled safely."""


@dataclass(frozen=True)
class ValidatedDestination:
    url: str
    parsed: SplitResult
    hostname: str
    port: int
    addresses: tuple[str, ...]


def _is_public_address(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_global
    except ValueError:
        return False


def validate_outbound_url(
    value: str,
    *,
    allow_http: bool = False,
    allow_private: bool = False,
    resolve: bool = True,
) -> ValidatedDestination:
    """Validate an HTTP(S) URL and optionally resolve every destination address."""
    if not isinstance(value, str) or not value or value != value.strip():
        raise UnsafeOutboundUrl("The URL is empty or contains surrounding whitespace.")
    if any(ord(character) < 32 or ord(character) == 127 for character in value):
        raise UnsafeOutboundUrl("Control characters are not allowed in outbound URLs.")

    parsed = urlsplit(value)
    allowed_schemes = {"https", "http"} if allow_http else {"https"}
    if parsed.scheme.lower() not in allowed_schemes:
        raise UnsafeOutboundUrl("The URL scheme is not allowed.")
    if not parsed.hostname or parsed.username is not None or parsed.password is not None:
        raise UnsafeOutboundUrl("The URL host is missing or contains credentials.")
    if parsed.fragment:
        raise UnsafeOutboundUrl("URL fragments are not allowed.")

    try:
        hostname = parsed.hostname.encode("idna").decode("ascii").lower()
        port = parsed.port or (443 if parsed.scheme.lower() == "https" else 80)
    except (UnicodeError, ValueError) as exc:
        raise UnsafeOutboundUrl("The URL host or port is invalid.") from exc
    if not 1 <= port <= 65535:
        raise UnsafeOutboundUrl("The URL port is invalid.")

    addresses: tuple[str, ...] = ()
    if resolve:
        try:
            resolved = socket.getaddrinfo(hostname, port, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeOutboundUrl("The outbound host could not be resolved.") from exc
        addresses = tuple(dict.fromkeys(item[4][0] for item in resolved))
        if not addresses:
            raise UnsafeOutboundUrl("The outbound host did not resolve to an address.")
        if not allow_private and any(not _is_public_address(address) for address in addresses):
            raise UnsafeOutboundUrl("The outbound host resolves to a non-public network.")

    return ValidatedDestination(
        url=value,
        parsed=parsed,
        hostname=hostname,
        port=port,
        addresses=addresses,
    )


class _PinnedHTTPSConnection(http.client.HTTPSConnection):
    def __init__(self, destination: ValidatedDestination, address: str, timeout: float):
        super().__init__(
            destination.hostname,
            destination.port,
            timeout=timeout,
            context=ssl.create_default_context(),
        )
        self._validated_address = address

    def connect(self) -> None:
        raw_socket = socket.create_connection(
            (self._validated_address, self.port),
            self.timeout,
            self.source_address,
        )
        try:
            self.sock = self._context.wrap_socket(raw_socket, server_hostname=self.host)
        except Exception:
            raw_socket.close()
            raise


def _request_target(parsed: SplitResult, query: Mapping[str, str] | None) -> str:
    existing_query = parsed.query
    added_query = urlencode(query or {})
    combined_query = "&".join(part for part in (existing_query, added_query) if part)
    return urlunsplit(("", "", parsed.path or "/", combined_query, ""))


def _host_header(destination: ValidatedDestination) -> str:
    host = destination.hostname
    if ":" in host:
        host = f"[{host}]"
    default_port = 443 if destination.parsed.scheme.lower() == "https" else 80
    return host if destination.port == default_port else f"{host}:{destination.port}"


def get_json(
    url: str,
    *,
    headers: Mapping[str, str] | None = None,
    query: Mapping[str, str] | None = None,
    allow_http: bool = False,
    allow_private: bool = False,
    connect_timeout: float = 3.0,
    read_timeout: float = 8.0,
    max_response_bytes: int = MAX_JSON_RESPONSE_BYTES,
) -> tuple[int, dict]:
    """GET JSON from a validated, DNS-pinned destination without redirects."""
    destination = validate_outbound_url(
        url,
        allow_http=allow_http,
        allow_private=allow_private,
        resolve=True,
    )
    address = destination.addresses[0]
    request_headers = {"Accept": "application/json", **(headers or {})}
    request_headers["Host"] = _host_header(destination)

    if destination.parsed.scheme.lower() == "https":
        connection: http.client.HTTPConnection = _PinnedHTTPSConnection(
            destination,
            address,
            connect_timeout,
        )
    else:
        connection = http.client.HTTPConnection(address, destination.port, timeout=connect_timeout)

    try:
        connection.connect()
        if connection.sock is not None:
            connection.sock.settimeout(read_timeout)
        connection.request("GET", _request_target(destination.parsed, query), headers=request_headers)
        response = connection.getresponse()
        body = response.read(max_response_bytes + 1)
        status = response.status
    except (OSError, http.client.HTTPException) as exc:
        raise OutboundResponseError("The outbound request failed.") from exc
    finally:
        connection.close()

    if len(body) > max_response_bytes:
        raise OutboundResponseError("The outbound response exceeded the size limit.")
    try:
        payload = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OutboundResponseError("The outbound response was not valid JSON.") from exc
    if not isinstance(payload, dict):
        raise OutboundResponseError("The outbound JSON response must be an object.")
    return status, payload
