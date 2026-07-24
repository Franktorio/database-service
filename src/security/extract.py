"""Helpers for extracting request-related data used across security modules."""

import ipaddress
from collections.abc import Iterable

from fastapi import Request


def _is_valid_ip_address(ip_address: str | None) -> bool:
    if not ip_address:
        return False
    try:
        ipaddress.ip_address(ip_address)
        return True
    except ValueError:
        return False


def extract_request_from_call(args: tuple, kwargs: dict) -> Request | None:
    for arg in args:
        if isinstance(arg, Request):
            return arg
    for value in kwargs.values():
        if isinstance(value, Request):
            return value
    return None


def extract_bearer_token(request: Request | None) -> str | None:
    if request is None:
        return None

    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None

    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer":
        return None

    stripped = token.strip()
    return stripped or None


def extract_cookie_value(request: Request | None, cookie_name: str) -> str | None:
    if request is None:
        return None
    cookie_value = request.cookies.get(cookie_name)
    if not cookie_value:
        return None
    stripped = cookie_value.strip()
    return stripped or None


def extract_client_ip(
    request: Request | None,
    trusted_proxies: Iterable[str] | None = None,
) -> str | None:
    if request is None:
        return None

    peer_ip = request.client.host if request.client else None
    trusted = set(trusted_proxies or ())

    if peer_ip in trusted:
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            forwarded_ip = forwarded_for.split(",")[0].strip()
            if _is_valid_ip_address(forwarded_ip):
                return forwarded_ip

        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            real_ip = real_ip.strip()
            if _is_valid_ip_address(real_ip):
                return real_ip

    if _is_valid_ip_address(peer_ip):
        return peer_ip

    return None