"""Subscriptions and usage counters."""

from __future__ import annotations

import pytest
from django.db import IntegrityError

from accounts.models import Organization
from billing.models import PlanCode, Subscription, UsageCounter
from billing.services import current_period_start


@pytest.mark.django_db
def test_new_subscriptions_start_on_the_free_demo_plan(organization: Organization) -> None:
    subscription = Subscription.objects.create(organization=organization)

    assert subscription.plan == PlanCode.FREE
    assert subscription.provider == "demo"


@pytest.mark.django_db
def test_one_usage_counter_per_month(organization: Organization) -> None:
    UsageCounter.objects.create(organization=organization, period_start=current_period_start())

    with pytest.raises(IntegrityError):
        UsageCounter.objects.create(organization=organization, period_start=current_period_start())
