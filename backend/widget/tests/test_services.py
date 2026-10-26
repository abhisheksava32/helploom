"""Origin rules, site key rotation, the embed snippet and the socket admission checks."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from channels.db import database_sync_to_async
from django.core.cache import cache
from rest_framework import exceptions

from accounts.models import Organization
from widget import services
from widget.models import SITE_KEY_PREFIX, WidgetConfig


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> None:
    cache.clear()


@pytest.fixture
def widget(organization: Organization) -> WidgetConfig:
    widget = services.create_widget(organization)
    widget.allowed_origins = ["https://shop.example.com"]
    widget.save()
    return widget


@pytest.mark.django_db
def test_listed_origins_are_allowed_and_others_are_not(widget: WidgetConfig) -> None:
    assert services.origin_is_allowed(widget, "https://shop.example.com")
    assert services.origin_is_allowed(widget, "https://SHOP.example.com:443")
    assert not services.origin_is_allowed(widget, "https://evil.example")
    assert not services.origin_is_allowed(widget, None)


@pytest.mark.django_db
def test_localhost_is_allowed_only_in_debug_with_the_flag(widget: WidgetConfig, settings: Any) -> None:
    settings.DEBUG = False
    assert not services.origin_is_allowed(widget, "http://localhost:5173")

    settings.DEBUG = True
    assert services.origin_is_allowed(widget, "http://localhost:5173")
    assert services.origin_is_allowed(widget, "http://127.0.0.1:8080")
    assert services.origin_is_allowed(widget, "http://[::1]:3000")
    assert not services.origin_is_allowed(widget, "https://localhost.evil.example")

    settings.WIDGET_ALLOW_LOCALHOST_IN_DEBUG = False
    assert not services.origin_is_allowed(widget, "http://localhost:5173")


@pytest.mark.django_db
def test_rotating_the_key_invalidates_the_old_one(widget: WidgetConfig) -> None:
    old_key = widget.site_key

    services.rotate_site_key(widget)

    assert widget.site_key.startswith(SITE_KEY_PREFIX)
    assert len(widget.site_key) == len(SITE_KEY_PREFIX) + 32
    assert services.get_active_widget(old_key) is None
    assert services.get_active_widget(widget.site_key) == widget


@pytest.mark.django_db
def test_disabled_widgets_are_not_served(widget: WidgetConfig) -> None:
    services.update_widget(widget, is_enabled=False)

    with pytest.raises(exceptions.NotFound):
        services.resolve_public_widget(widget.site_key, "https://shop.example.com")


@pytest.mark.django_db
def test_public_widget_resolution_checks_the_origin(widget: WidgetConfig) -> None:
    assert services.resolve_public_widget(widget.site_key, "https://shop.example.com") == widget
    with pytest.raises(exceptions.PermissionDenied) as excinfo:
        services.resolve_public_widget(widget.site_key, "https://evil.example")
    assert excinfo.value.get_codes() == "origin_not_allowed"


@pytest.mark.django_db
def test_embed_snippet_points_at_the_configured_urls(widget: WidgetConfig, settings: Any) -> None:
    snippet = services.embed_snippet(widget)

    assert snippet == (
        f'<script src="{settings.FRONTEND_URL}/widget.js" data-site-key="{widget.site_key}" '
        f'data-api-url="{settings.BACKEND_URL}" data-ws-url="{settings.PUBLIC_WS_URL}" defer></script>'
    )


@pytest.mark.parametrize(
    ("raw", "kept"),
    [
        ("v_abcdefghijklmnop", True),
        ("short", False),
        ("has spaces in it ok?", False),
        ("x" * 65, False),
        (None, False),
    ],
)
def test_visitor_ids_are_kept_only_when_well_formed(raw: str | None, kept: bool) -> None:
    cleaned = services.clean_visitor_id(raw)

    assert (cleaned == raw) is kept
    assert services.clean_visitor_id(cleaned) == cleaned


@pytest.mark.django_db(transaction=True)
async def test_admission_outcomes(make_organization: Callable[..., Organization]) -> None:
    organization = await database_sync_to_async(make_organization)()
    widget = await database_sync_to_async(services.create_widget)(organization)
    await database_sync_to_async(services.update_widget)(widget, allowed_origins=["https://shop.example.com"])

    ok = await services.admit_connection(
        site_key=widget.site_key, origin="https://shop.example.com", ip="1.1.1.1"
    )
    foreign = await services.admit_connection(
        site_key=widget.site_key, origin="https://evil.example", ip="1.1.1.1"
    )
    unknown = await services.admit_connection(
        site_key="hlp_pk_nope", origin="https://x.example", ip="1.1.1.1"
    )

    assert ok.outcome == services.Admission.OK
    assert ok.widget is not None and ok.widget.organization_id == organization.id
    assert foreign.outcome == services.Admission.ORIGIN_NOT_ALLOWED
    assert unknown.outcome == services.Admission.INVALID_SITE_KEY


@pytest.mark.django_db(transaction=True)
async def test_connections_are_rate_limited_per_ip(
    make_organization: Callable[..., Organization], settings: Any
) -> None:
    settings.WIDGET_CONNECTIONS_PER_MINUTE = 2
    organization = await database_sync_to_async(make_organization)()
    widget = await database_sync_to_async(services.create_widget)(organization)
    await database_sync_to_async(services.update_widget)(widget, allowed_origins=["https://shop.example.com"])

    outcomes = [
        (
            await services.admit_connection(
                site_key=widget.site_key, origin="https://shop.example.com", ip=ip
            )
        ).outcome
        for ip in ["2.2.2.2", "2.2.2.2", "2.2.2.2", "3.3.3.3"]
    ]

    assert outcomes == [
        services.Admission.OK,
        services.Admission.OK,
        services.Admission.THROTTLED,
        services.Admission.OK,
    ]
