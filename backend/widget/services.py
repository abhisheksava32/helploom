"""Widget business logic: settings, site keys, the public config and the checks that
guard the public socket.

Site keys are public (they ship in the customer's page source). What protects the
widget is the organisation's origin allow list, per IP rate limits and plan quotas.
The socket checks live here, not in the consumer, so any consumer that serves widget
visitors applies exactly the same rules:

    admission = await admit_connection(site_key=..., origin=..., ip=...)
    await check_message_rate(ip)
    widget = await aget_active_widget(site_key)   # re-checked per frame: rotation is instant
"""

from __future__ import annotations

import re
import secrets
from dataclasses import dataclass
from enum import StrEnum
from html import escape
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from channels.db import database_sync_to_async
from django.conf import settings
from rest_framework import exceptions

from core import ratelimit
from core.origins import normalize_origin, origin_allowed

from .models import WidgetConfig, generate_site_key

if TYPE_CHECKING:
    from accounts.models import Organization

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}
_VISITOR_ID = re.compile(r"^[A-Za-z0-9_-]{16,64}$")


# Dashboard settings


def create_widget(organization: Organization) -> WidgetConfig:
    widget, _ = WidgetConfig.objects.get_or_create(organization=organization)
    return widget


def get_widget(organization: Organization) -> WidgetConfig:
    # Organisations made outside signup (admin, fixtures) get their widget on first use.
    return create_widget(organization)


def update_widget(widget: WidgetConfig, **changes: Any) -> WidgetConfig:
    """changes are validated by WidgetSettingsUpdateSerializer, origins already normalised."""
    for field, value in changes.items():
        setattr(widget, field, value)
    if changes:
        widget.save(update_fields=[*changes, "updated_at"])
    return widget


def rotate_site_key(widget: WidgetConfig) -> WidgetConfig:
    """Open sockets with the old key are refused on their next frame."""
    widget.site_key = generate_site_key()
    widget.save(update_fields=["site_key", "updated_at"])
    return widget


def script_url() -> str:
    return f"{settings.FRONTEND_URL}/widget.js"


def ws_url() -> str:
    return f"{settings.PUBLIC_WS_URL}/ws/widget/"


def embed_snippet(widget: WidgetConfig) -> str:
    attributes = {
        "src": script_url(),
        "data-site-key": widget.site_key,
        "data-api-url": settings.BACKEND_URL,
        "data-ws-url": settings.PUBLIC_WS_URL,
    }
    rendered = " ".join(f'{name}="{escape(value, quote=True)}"' for name, value in attributes.items())
    return f"<script {rendered} defer></script>"


# Origin rules


def is_local_origin(origin: str | None) -> bool:
    normalized = normalize_origin(origin)
    if normalized is None:
        return False
    parts = urlsplit(normalized)
    return parts.scheme == "http" and parts.hostname in _LOCAL_HOSTS


def origin_is_allowed(widget: WidgetConfig, origin: str | None) -> bool:
    if origin_allowed(origin, widget.allowed_origins):
        return True
    # Lets a developer try the widget from any local page without editing settings.
    local_ok = settings.DEBUG and settings.WIDGET_ALLOW_LOCALHOST_IN_DEBUG
    return bool(local_ok and is_local_origin(origin))


def get_active_widget(site_key: str | None) -> WidgetConfig | None:
    """The enabled widget for a site key, with its organisation, or None."""
    if not site_key or len(site_key) > 64:
        return None
    return (
        WidgetConfig.objects.select_related("organization").filter(site_key=site_key, is_enabled=True).first()
    )


aget_active_widget = database_sync_to_async(get_active_widget)


def resolve_public_widget(site_key: str | None, origin: str | None) -> WidgetConfig:
    """For GET /widget/public/config/. Unknown and disabled keys look the same."""
    widget = get_active_widget(site_key)
    if widget is None:
        raise exceptions.NotFound("This widget does not exist or is turned off.")
    if not origin_is_allowed(widget, origin):
        raise exceptions.PermissionDenied(
            "This website is not allowed to use this widget. Add it to the allowed origins in "
            "the Helploom widget settings.",
            code="origin_not_allowed",
        )
    return widget


def public_config(widget: WidgetConfig) -> dict[str, Any]:
    return {
        "organization_name": widget.organization.name,
        "title": widget.title,
        "greeting": widget.greeting,
        "brand_color": widget.brand_color,
        "position": widget.position,
        "ws_url": ws_url(),
    }


# Public socket checks


class Admission(StrEnum):
    OK = "ok"
    ORIGIN_NOT_ALLOWED = "origin_not_allowed"
    THROTTLED = "throttled"
    INVALID_SITE_KEY = "invalid_site_key"


@dataclass(frozen=True)
class AdmissionResult:
    outcome: Admission
    widget: WidgetConfig | None = None
    retry_after: int = 0


async def admit_connection(*, site_key: str | None, origin: str | None, ip: str) -> AdmissionResult:
    """The ws/widget/ handshake, in the order docs/API.md fixes.

    1. The Origin must be allowed for the key's organisation. An unknown key has no
       allow list to compare with, so it falls through to step 3.
    2. At most WIDGET_CONNECTIONS_PER_MINUTE connections per IP.
    3. The key must exist and the widget must be enabled.
    """
    widget = await aget_active_widget(site_key)
    if widget is not None and not origin_is_allowed(widget, origin):
        return AdmissionResult(Admission.ORIGIN_NOT_ALLOWED)
    limit = await ratelimit.ahit(
        f"widget:connect:{ratelimit.hash_ip(ip)}", settings.WIDGET_CONNECTIONS_PER_MINUTE
    )
    if not limit.allowed:
        return AdmissionResult(Admission.THROTTLED, retry_after=limit.retry_after)
    if widget is None:
        return AdmissionResult(Admission.INVALID_SITE_KEY)
    return AdmissionResult(Admission.OK, widget=widget)


async def check_message_rate(ip: str) -> ratelimit.RateLimitResult:
    return await ratelimit.ahit(
        f"widget:message:{ratelimit.hash_ip(ip)}", settings.WIDGET_MESSAGES_PER_MINUTE
    )


def new_visitor_id() -> str:
    return f"v_{secrets.token_urlsafe(18)}"


def clean_visitor_id(raw: str | None) -> str:
    """Keep a well formed id from the widget's localStorage, otherwise issue a new one."""
    if raw and _VISITOR_ID.fullmatch(raw):
        return raw
    return new_visitor_id()
