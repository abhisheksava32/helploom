"""The refresh token cookie. httpOnly so page scripts never see it, scoped to
/api/v1/auth/ so it only travels to the endpoints that use it."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, Literal, cast

from django.conf import settings
from django.http import HttpResponseBase

SameSite = Literal["Lax", "Strict", "None"]


def _samesite() -> SameSite:
    return cast(SameSite, settings.REFRESH_COOKIE_SAMESITE)


def set_refresh_cookie(response: HttpResponseBase, refresh_token: str) -> None:
    lifetime = cast(timedelta, settings.SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
    response.set_cookie(
        settings.REFRESH_COOKIE_NAME,
        refresh_token,
        max_age=int(lifetime.total_seconds()),
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        secure=settings.REFRESH_COOKIE_SECURE,
        httponly=True,
        samesite=_samesite(),
    )


def clear_refresh_cookie(response: HttpResponseBase) -> None:
    response.delete_cookie(
        settings.REFRESH_COOKIE_NAME,
        path=settings.REFRESH_COOKIE_PATH,
        domain=settings.REFRESH_COOKIE_DOMAIN,
        samesite=_samesite(),
    )


def read_refresh_cookie(request: Any) -> str | None:
    value = request.COOKIES.get(settings.REFRESH_COOKIE_NAME)
    return str(value) if value else None
