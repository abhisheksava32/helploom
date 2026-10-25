"""Helpers shared by test suites across apps (fixtures themselves live in conftest.py)."""

from __future__ import annotations

from typing import TYPE_CHECKING

from rest_framework_simplejwt.tokens import AccessToken

if TYPE_CHECKING:
    from accounts.models import User


def access_token_for(user: User) -> str:
    """A valid access JWT, as the dashboard would send it."""
    return str(AccessToken.for_user(user))
