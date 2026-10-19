"""Separate authenticated control endpoints from private bulk transfer origins."""

import ipaddress
import re
from urllib.parse import urlsplit


def endpoint(value, *, private=False):
    if not isinstance(value, str) or any(c.isspace() or ord(c) < 32 or ord(c) == 127 for c in value):
        raise ValueError("Endpoint cannot contain whitespace or control characters")
    parsed = urlsplit(value)
    try:
        port = parsed.port
    except ValueError:
        raise ValueError("Invalid endpoint port") from None
    if (
        parsed.scheme not in ("http", "https")
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
        or (port is not None and not 1 <= port <= 65535)
    ):
        raise ValueError("Use an endpoint origin without credentials, path or query")
    try:
        address = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        if private:
            raise ValueError("Use a numeric private/Tailscale address") from None
        if parsed.scheme != "https" or not re.fullmatch(
            r"(?=.{1,253}$)(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)+[a-zA-Z]{2,63}", parsed.hostname
        ):
            raise ValueError("Public control requires an HTTPS hostname")
    else:
        allowed = (address.is_private or address in ipaddress.ip_network("100.64.0.0/10")) and not (
            address.is_unspecified or address.is_multicast or (address.is_reserved and not address.is_loopback)
        )
        if private and not allowed:
            raise ValueError("Use a private/Tailscale endpoint")
        if not allowed and parsed.scheme != "https":
            raise ValueError("Public control requires HTTPS")
    return value.rstrip("/")


def is_private(value):
    try:
        endpoint(value, private=True)
        return True
    except ValueError:
        return False
