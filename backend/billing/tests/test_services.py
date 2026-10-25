"""Plan limits and usage metering used by the other apps."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

import pytest
from django.utils import timezone

from accounts.models import Invitation, Membership, Organization
from billing import services
from billing.models import Subscription
from billing.plans import PLANS, get_plan
from core.exceptions import PlanLimitExceeded


def test_unknown_plan_codes_fall_back_to_free() -> None:
    assert get_plan("enterprise") == PLANS["free"]


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
    assert excinfo.value.details["limit"] == "messages"


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

    assert services.seats_used(organization.id) == 3
    with pytest.raises(PlanLimitExceeded):
        services.ensure_seat_quota(organization)  # Free has 2 seats


@pytest.mark.django_db
def test_usage_snapshot_reports_used_and_limits(organization: Organization) -> None:
    snapshot = services.usage_snapshot(organization.id)

    assert snapshot["documents"] == {"used": 0, "limit": PLANS["free"].documents}
    assert snapshot["seats"]["used"] == 1
