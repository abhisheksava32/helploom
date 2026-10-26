"""The Widget endpoints in docs/API.md: settings, key rotation and the public config."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, Organization, Role
from widget import services
from widget.models import WidgetConfig


@pytest.fixture
def widget(organization: Organization) -> WidgetConfig:
    return services.update_widget(
        services.create_widget(organization), allowed_origins=["https://shop.example.com"]
    )


@pytest.mark.django_db
def test_agents_read_the_widget_settings(
    owner: Membership,
    widget: WidgetConfig,
    make_member: Callable[..., Membership],
    client_for: Callable[..., Any],
) -> None:
    agent = client_for(make_member(organization=owner.organization, role=Role.AGENT))

    body = agent.get("/api/v1/widget/config/").json()

    assert set(body) == {
        "site_key",
        "is_enabled",
        "allowed_origins",
        "title",
        "greeting",
        "brand_color",
        "position",
        "script_url",
        "ws_url",
        "embed_snippet",
        "updated_at",
    }
    assert body["site_key"] == widget.site_key
    assert body["ws_url"] == "ws://localhost:8000/ws/widget/"
    assert widget.site_key in body["embed_snippet"]
    assert agent.patch("/api/v1/widget/config/", {"title": "x"}, format="json").status_code == 403


@pytest.mark.django_db
def test_admins_update_settings_with_normalised_origins(auth_client: APIClient, widget: WidgetConfig) -> None:
    response = auth_client.patch(
        "/api/v1/widget/config/",
        {
            "allowed_origins": [
                "https://Shop.Example.com:443/",
                "https://shop.example.com",
                "http://localhost:3000",
            ],
            "brand_color": "#0F766E",
            "title": "Northwind help",
            "position": "left",
        },
        format="json",
    )

    assert response.status_code == 200
    body = response.json()
    assert body["allowed_origins"] == ["https://shop.example.com", "http://localhost:3000"]
    assert body["brand_color"] == "#0f766e"
    assert body["position"] == "left"


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("payload", "field"),
    [
        ({"allowed_origins": ["https://shop.example.com/help"]}, "allowed_origins"),
        ({"allowed_origins": ["shop.example.com"]}, "allowed_origins"),
        ({"allowed_origins": [f"https://s{i}.example.com" for i in range(21)]}, "allowed_origins"),
        ({"brand_color": "purple"}, "brand_color"),
        ({"title": ""}, "title"),
        ({"greeting": "x" * 301}, "greeting"),
        ({"position": "top"}, "position"),
    ],
)
def test_invalid_settings_are_rejected(
    auth_client: APIClient, widget: WidgetConfig, payload: Any, field: str
) -> None:
    response = auth_client.patch("/api/v1/widget/config/", payload, format="json")

    assert response.status_code == 400
    assert field in response.json()["error"]["details"]


@pytest.mark.django_db
def test_rotate_key(auth_client: APIClient, widget: WidgetConfig) -> None:
    response = auth_client.post("/api/v1/widget/config/rotate-key/")

    assert response.status_code == 200
    assert response.json()["site_key"] != widget.site_key


@pytest.mark.django_db
def test_public_config_echoes_an_allowed_origin(api_client: APIClient, widget: WidgetConfig) -> None:
    response = api_client.get(
        f"/api/v1/widget/public/config/?site_key={widget.site_key}", HTTP_ORIGIN="https://shop.example.com"
    )

    assert response.status_code == 200
    assert response.json() == {
        "organization_name": widget.organization.name,
        "title": "Help",
        "greeting": widget.greeting,
        "brand_color": "#4f46e5",
        "position": "right",
        "ws_url": "ws://localhost:8000/ws/widget/",
    }
    assert response["Access-Control-Allow-Origin"] == "https://shop.example.com"
    assert "origin" in response["Vary"].lower()


@pytest.mark.django_db
def test_public_config_refuses_other_origins_and_unknown_keys(
    api_client: APIClient, widget: WidgetConfig
) -> None:
    url = f"/api/v1/widget/public/config/?site_key={widget.site_key}"

    foreign = api_client.get(url, HTTP_ORIGIN="https://evil.example")
    missing = api_client.get(url)
    unknown = api_client.get(
        "/api/v1/widget/public/config/?site_key=hlp_pk_unknown", HTTP_ORIGIN="https://shop.example.com"
    )
    no_key = api_client.get("/api/v1/widget/public/config/", HTTP_ORIGIN="https://shop.example.com")

    for response in (foreign, missing):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "origin_not_allowed"
        assert "Access-Control-Allow-Origin" not in response
    assert unknown.status_code == 404
    assert no_key.status_code == 404


@pytest.mark.django_db
def test_widget_settings_belong_to_the_callers_organization(
    auth_client: APIClient, widget: WidgetConfig, make_organization: Callable[..., Organization]
) -> None:
    other = services.create_widget(make_organization())

    body = auth_client.get("/api/v1/widget/config/").json()

    assert body["site_key"] == widget.site_key != other.site_key
