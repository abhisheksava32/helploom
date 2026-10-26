"""The Billing endpoints in docs/API.md: plans, subscription, checkout and the webhook."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, Role
from billing.tests.test_services import WEBHOOK_SECRET, event, signed


@pytest.mark.django_db
def test_plans_are_public(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/billing/plans/")

    assert response.status_code == 200
    starter = response.json()["results"][1]
    assert starter == {
        "code": "starter",
        "name": "Starter",
        "price_monthly_cents": 2900,
        "currency": "usd",
        "limits": {"messages_per_month": 3000, "documents": 100, "seats": 5},
        "features": ["Everything in Free", "Claude API answers", "Handoff tickets", "Full reports"],
    }


@pytest.mark.django_db
def test_subscription_shape(auth_client: APIClient) -> None:
    body = auth_client.get("/api/v1/billing/subscription/").json()

    assert set(body) == {
        "plan",
        "status",
        "provider",
        "billing_mode",
        "current_period_start",
        "current_period_end",
        "cancel_at_period_end",
        "usage",
    }
    assert body["plan"]["code"] == "free"
    assert (body["status"], body["provider"], body["billing_mode"]) == ("active", "demo", "demo")
    assert body["current_period_start"] is None
    assert set(body["usage"]) == {"period_start", "messages", "documents", "seats"}


@pytest.mark.django_db
def test_demo_checkout_is_owner_only(
    owner: Membership,
    make_member: Callable[..., Membership],
    client_for: Callable[..., APIClient],
    auth_client: APIClient,
) -> None:
    admin = client_for(make_member(organization=owner.organization, role=Role.ADMIN))

    denied = admin.post("/api/v1/billing/checkout/", {"plan": "pro"}, format="json")
    switched = auth_client.post("/api/v1/billing/checkout/", {"plan": "pro"}, format="json")
    unchanged = auth_client.post("/api/v1/billing/checkout/", {"plan": "pro"}, format="json")
    unknown = auth_client.post("/api/v1/billing/checkout/", {"plan": "enterprise"}, format="json")

    assert denied.status_code == 403
    assert switched.status_code == 200
    assert switched.json()["mode"] == "demo"
    assert switched.json()["checkout_url"] is None
    assert switched.json()["subscription"]["plan"]["code"] == "pro"
    assert unchanged.status_code == 409
    assert unchanged.json()["error"]["code"] == "plan_unchanged"
    assert unknown.status_code == 400


@pytest.mark.django_db
def test_portal_is_unavailable_in_demo_mode(auth_client: APIClient) -> None:
    response = auth_client.post("/api/v1/billing/portal/")

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "billing_portal_unavailable"


@pytest.mark.django_db
def test_webhook_accepts_signed_events_and_rejects_others(api_client: APIClient, settings: Any) -> None:
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    payload, signature = signed(event("evt_view", "invoice.paid", {}))

    ok = api_client.post(
        "/api/v1/billing/webhook/", payload, content_type="application/json", HTTP_STRIPE_SIGNATURE=signature
    )
    bad = api_client.post(
        "/api/v1/billing/webhook/", payload, content_type="application/json", HTTP_STRIPE_SIGNATURE="t=1,v1=x"
    )

    assert ok.status_code == 200
    assert ok.json() == {"received": True}
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_signature"
