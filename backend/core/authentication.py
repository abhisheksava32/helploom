"""Authentication helpers for public endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework.authentication import BaseAuthentication


class PublicEndpointAuthentication(BaseAuthentication):
    """For public endpoints that can still answer 401, such as login and refresh.

    It authenticates nobody, so a stale Authorization header cannot block a login. It
    only supplies the WWW-Authenticate challenge, without which DRF turns every 401
    into a 403.
    """

    def authenticate(self, request: Any) -> None:
        return None

    def authenticate_header(self, request: Any) -> str:
        return 'Bearer realm="api"'
