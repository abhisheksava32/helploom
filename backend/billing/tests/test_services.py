"""Plan limits, usage metering, plan changes in both billing modes and Stripe webhooks."""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from django.utils import timezone

from accounts.models import Invitation, Membership, Organization
from billing import services, stripe_client
from billing.models import StripeEvent, Subscription
from billing.plans import PLANS, get_plan
from core.exceptions import Conflict, PlanLimitExceeded

WEBHOOK_SECRET = "whsec_test_secret"


def test_unknown_plan_codes_fall_back_to_free() -> None:
    assert get_plan("enterprise") == PLANS["free"]


def test_plans_are_listed_cheapest_first() -> None:
    assert [plan.code for plan in services.list_plans()] == ["free", "starter", "pro"]


def test_periods_start_on_the_first_of_the_month_in_utc() -> None:
    assert (
        services.current_period_start(datetime(2026, 3, 31, 23, 30, tzinfo=UTC)).isoformat() == "2026-03-01"
    )


@pytest.mark.django_db
def test_message_quota_counts_and_then_refuses(organization: Organization) -> None:
    Subscription.objects.create(organization=organization)
    limit = PLANS["free"].messages_per_month
    services.UsageCounter.objects.create(
        organization=organization, period_start=services.current_period_start(), messages=limit - 1
    )

    services.consume_message_quota(organization.id)
    assert services.messages_used(organization.id) == limit

    with pytest.raises(PlanLimitExceeded) as excinfo:
        services.consume_message_quota(organization.id)
    assert excinfo.value.details == {"limit": "messages", "used": limit, "allowed": limit, "plan": "free"}


@pytest.mark.django_db
def test_document_quota_counts_the_files_being_added(organization: Organization) -> None:
    services.ensure_document_quota(organization, adding=PLANS["free"].documents)

    with pytest.raises(PlanLimitExceeded) as excinfo:
        services.ensure_document_quota(organization, adding=PLANS["free"].documents + 1)
    assert excinfo.value.details["limit"] == "documents"


@pytest.mark.django_db
def test_seats_include_pending_invitations(owner: Membership, make_member: Callable[..., Membership]) -> None:
    organization = owner.organization
    make_member(organization=organization, role="agent")
    Invitation.objects.create(
        organization=organization,
        email="pending@example.com",
        token_hash="a" * 64,
        expires_at=timezone.now() + timedelta(days=1),
    )
    Invitation.objects.create(
        organization=organization,
        email="expired@example.com",
        token_hash="b" * 64,
        expires_at=timezone.now() - timedelta(days=1),
    )

    assert services.seats_used(organization.id) == 3
    with pytest.raises(PlanLimitExceeded):
        services.ensure_seat_quota(organization)  # Free has 2 seats


@pytest.mark.django_db
def test_usage_snapshot_reports_used_and_limits(organization: Organization) -> None:
    snapshot = services.usage_snapshot(organization.id)

    assert snapshot["documents"] == {"used": 0, "limit": PLANS["free"].documents}
    assert snapshot["seats"]["used"] == 1
    assert snapshot["period_start"] == services.current_period_start().isoformat()


# Plan changes


@pytest.mark.django_db
def test_demo_checkout_switches_at_once_and_publishes(
    organization: Organization, monkeypatch: pytest.MonkeyPatch, django_capture_on_commit_callbacks: Any
) -> None:
    events: list[tuple[Any, dict[str, Any]]] = []
    monkeypatch.setattr(services, "broadcast_org_event", lambda org_id, event: events.append((org_id, event)))

    with django_capture_on_commit_callbacks(execute=True):
        result = services.start_checkout(organization, "pro")

    assert (result.mode, result.checkout_url) == ("demo", None)
    assert result.subscription.plan == "pro"
    assert events[0][0] == organization.id
    assert events[0][1]["type"] == "subscription.updated"
    assert events[0][1]["subscription"]["plan"]["code"] == "pro"


@pytest.mark.django_db
def test_switching_to_the_current_plan_conflicts(organization: Organization) -> None:
    with pytest.raises(Conflict) as excinfo:
        services.start_checkout(organization, "free")

    assert excinfo.value.get_codes() == "plan_unchanged"


@pytest.mark.django_db
def test_downgrades_are_blocked_while_usage_exceeds_the_target(
    owner: Membership, make_member: Callable[..., Membership]
) -> None:
    organization = owner.organization
    services.start_checkout(organization, "starter")
    for _ in range(2):
        make_member(organization=organization, role="agent")  # 3 seats in use, Free allows 2

    with pytest.raises(Conflict) as excinfo:
        services.start_checkout(organization, "free")

    assert excinfo.value.get_codes() == "plan_downgrade_blocked"
    assert excinfo.value.details == {"limit": "seats", "used": 3, "allowed": 2}


@pytest.fixture
def stripe_mode(settings: Any) -> Any:
    settings.STRIPE_SECRET_KEY = "sk_test_123"
    settings.STRIPE_WEBHOOK_SECRET = WEBHOOK_SECRET
    settings.STRIPE_PRICE_STARTER = "price_starter"
    settings.STRIPE_PRICE_PRO = "price_pro"
    return settings


@pytest.mark.django_db
def test_stripe_checkout_returns_a_session_url_and_waits_for_the_webhook(
    organization: Organization, stripe_mode: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_session(**kwargs: Any) -> str:
        calls.append(kwargs)
        return "https://checkout.stripe.com/c/pay/cs_test"

    monkeypatch.setattr(stripe_client, "create_checkout_session", fake_session)

    result = services.start_checkout(organization, "starter", customer_email="ada@example.com")

    assert (result.mode, result.checkout_url) == ("stripe", "https://checkout.stripe.com/c/pay/cs_test")
    assert result.subscription.plan == "free"
    assert calls[0]["price_id"] == "price_starter"
    assert calls[0]["organization_id"] == str(organization.id)
    assert calls[0]["success_url"].endswith("/app/settings/billing?checkout=success")
    assert calls[0]["cancel_url"].endswith("/app/settings/billing?checkout=cancelled")


@pytest.mark.django_db
def test_paid_stripe_subscriptions_change_in_the_portal(
    organization: Organization, stripe_mode: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    Subscription.objects.create(
        organization=organization,
        plan="starter",
        provider="stripe",
        stripe_customer_id="cus_1",
        stripe_subscription_id="sub_1",
    )
    monkeypatch.setattr(
        stripe_client, "create_portal_session", lambda **kw: f"https://billing.stripe.com/{kw['customer_id']}"
    )

    with pytest.raises(Conflict) as excinfo:
        services.start_checkout(organization, "pro")

    assert excinfo.value.get_codes() == "use_billing_portal"
    assert services.billing_portal_url(organization) == "https://billing.stripe.com/cus_1"


@pytest.mark.django_db
def test_the_portal_is_unavailable_in_demo_mode(organization: Organization) -> None:
    with pytest.raises(Conflict) as excinfo:
        services.billing_portal_url(organization)

    assert excinfo.value.get_codes() == "billing_portal_unavailable"


# Webhooks


def signed(event: dict[str, Any], secret: str = WEBHOOK_SECRET) -> tuple[bytes, str]:
    payload = json.dumps(event)
    timestamp = int(time.time())
    signature = hmac.new(secret.encode(), f"{timestamp}.{payload}".encode(), hashlib.sha256).hexdigest()
    return payload.encode(), f"t={timestamp},v1={signature}"


def event(event_id: str, kind: str, obj: dict[str, Any]) -> dict[str, Any]:
    return {"id": event_id, "type": kind, "data": {"object": obj}}


@pytest.mark.django_db
def test_webhook_signatures_are_verified(stripe_mode: Any) -> None:
    payload, _ = signed(event("evt_1", "invoice.paid", {}))
    _, wrong = signed(event("evt_1", "invoice.paid", {}), secret="whsec_other")

    for signature in (wrong, None, "t=1,v1=deadbeef"):
        with pytest.raises(stripe_client.InvalidSignature):
            services.handle_stripe_webhook(payload, signature)
    assert not StripeEvent.objects.exists()


@pytest.mark.django_db
def test_checkout_completion_upgrades_the_plan_once(organization: Organization, stripe_mode: Any) -> None:
    services.create_subscription(organization)
    completed = event(
        "evt_checkout",
        "checkout.session.completed",
        {
            "client_reference_id": str(organization.id),
            "customer": "cus_9",
            "subscription": "sub_9",
            "metadata": {"organization_id": str(organization.id), "plan": "pro"},
        },
    )

    services.handle_stripe_webhook(*signed(completed))
    subscription = Subscription.objects.get(organization=organization)
    assert (subscription.plan, subscription.provider) == ("pro", "stripe")
    assert (subscription.stripe_customer_id, subscription.stripe_subscription_id) == ("cus_9", "sub_9")

    # A retried delivery of the same event changes nothing.
    Subscription.objects.filter(pk=subscription.pk).update(plan="starter")
    services.handle_stripe_webhook(*signed(completed))
    assert Subscription.objects.get(pk=subscription.pk).plan == "starter"
    assert StripeEvent.objects.get(event_id="evt_checkout").processed_at is not None


@pytest.mark.django_db
def test_subscription_lifecycle_events(organization: Organization, stripe_mode: Any) -> None:
    Subscription.objects.create(organization=organization, stripe_customer_id="cus_5")
    period_end = int(time.time()) + 30 * 86400
    stripe_sub = {
        "id": "sub_5",
        "customer": "cus_5",
        "status": "active",
        "cancel_at_period_end": True,
        "metadata": {"organization_id": str(organization.id)},
        "items": {
            "data": [
                {
                    "price": {"id": "price_pro"},
                    "current_period_start": period_end - 30 * 86400,
                    "current_period_end": period_end,
                }
            ]
        },
    }

    services.handle_stripe_webhook(*signed(event("evt_a", "customer.subscription.updated", stripe_sub)))
    subscription = Subscription.objects.get(organization=organization)
    assert (subscription.plan, subscription.status, subscription.cancel_at_period_end) == (
        "pro",
        "active",
        True,
    )
    assert subscription.current_period_end == datetime.fromtimestamp(period_end, tz=UTC)

    services.handle_stripe_webhook(
        *signed(
            event(
                "evt_b",
                "invoice.payment_failed",
                {"customer": "cus_5", "parent": {"subscription_details": {"subscription": "sub_5"}}},
            )
        )
    )
    assert Subscription.objects.get(pk=subscription.pk).status == "past_due"

    services.handle_stripe_webhook(
        *signed(event("evt_c", "customer.subscription.deleted", {"id": "sub_5", "customer": "cus_5"}))
    )
    subscription.refresh_from_db()
    assert (subscription.plan, subscription.status, subscription.stripe_subscription_id) == (
        "free",
        "canceled",
        "",
    )
    assert subscription.stripe_customer_id == "cus_5"


@pytest.mark.django_db
def test_events_for_unknown_customers_are_recorded_and_ignored(stripe_mode: Any) -> None:
    services.handle_stripe_webhook(
        *signed(
            event(
                "evt_x",
                "customer.subscription.updated",
                {"id": "sub_x", "customer": "cus_x", "status": "active"},
            )
        )
    )

    assert StripeEvent.objects.get(event_id="evt_x").processed_at is not None
