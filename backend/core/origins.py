"""Origin parsing shared by CORS-like checks on websockets."""

from __future__ import annotations

from collections.abc import Iterable
from urllib.parse import urlsplit

_DEFAULT_PORTS = {"http": 80, "https": 443}


def normalize_origin(value: str | None) -> str | None:
    """Return "scheme://host[:port]" in lower case, or None when value is not an origin.

    Default ports are dropped so "https://shop.example:443" equals "https://shop.example".
    Paths, queries and credentials make the value invalid rather than being ignored,
    so a mistyped allowed origin fails loudly in validation.
    """
    if not value:
        return None
    try:
        parts = urlsplit(value.strip())
        port = parts.port
    except ValueError:
        return None
    scheme = parts.scheme.lower()
    host = (parts.hostname or "").lower()
    if scheme not in _DEFAULT_PORTS or not host:
        return None
    if parts.username or parts.password or parts.query or parts.fragment:
        return None
    if parts.path not in ("", "/"):
        return None
    if port is None or port == _DEFAULT_PORTS[scheme]:
        return f"{scheme}://{host}"
    return f"{scheme}://{host}:{port}"


def origin_allowed(origin: str | None, allowed: Iterable[str]) -> bool:
    candidate = normalize_origin(origin)
    if candidate is None:
        return False
    return any(candidate == normalize_origin(item) for item in allowed)


def scope_origin(scope: dict) -> str | None:
    """Read the Origin header from an ASGI scope."""
    for name, value in scope.get("headers", []):
        if name == b"origin":
            return value.decode("latin-1")
    return None
