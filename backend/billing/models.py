"""Subscriptions, monthly usage counters and processed Stripe events."""

from __future__ import annotations

from django.db import models

from core.models import TimeStampedModel, UUIDModel


class PlanCode(models.TextChoices):
    FREE = "free", "Free"
    STARTER = "starter", "Starter"
    PRO = "pro", "Pro"


class SubscriptionStatus(models.TextChoices):
    ACTIVE = "active", "Active"
    TRIALING = "trialing", "Trialing"
    PAST_DUE = "past_due", "Past due"
    CANCELED = "canceled", "Canceled"
    INCOMPLETE = "incomplete", "Incomplete"


class BillingProvider(models.TextChoices):
    DEMO = "demo", "Demo"
    STRIPE = "stripe", "Stripe"


class Subscription(TimeStampedModel):
    organization = models.OneToOneField(
        "accounts.Organization", on_delete=models.CASCADE, related_name="subscription"
    )
    plan = models.CharField(max_length=10, choices=PlanCode.choices, default=PlanCode.FREE)
    status = models.CharField(
        max_length=12, choices=SubscriptionStatus.choices, default=SubscriptionStatus.ACTIVE
    )
    provider = models.CharField(max_length=6, choices=BillingProvider.choices, default=BillingProvider.DEMO)
    stripe_customer_id = models.CharField(max_length=255, blank=True, db_index=True)
    stripe_subscription_id = models.CharField(max_length=255, blank=True, db_index=True)
    current_period_start = models.DateTimeField(null=True, blank=True)
    current_period_end = models.DateTimeField(null=True, blank=True)
    cancel_at_period_end = models.BooleanField(default=False)

    def __str__(self) -> str:
        return f"{self.organization_id} on {self.plan}"


class UsageCounter(UUIDModel):
    """Messages answered per organisation per calendar month (UTC). Documents and seats
    are counted live from their own tables instead."""

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="usage_counters"
    )
    period_start = models.DateField(help_text="First day of the month.")
    messages = models.PositiveIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-period_start"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "period_start"], name="billing_usage_unique_period"
            ),
        ]

    def __str__(self) -> str:
        return f"{self.organization_id} {self.period_start:%Y-%m}: {self.messages} messages"


class StripeEvent(models.Model):
    """Webhook idempotency: Stripe retries deliveries, we process each event id once."""

    event_id = models.CharField(max_length=255, primary_key=True)
    type = models.CharField(max_length=100)
    payload = models.JSONField()
    received_at = models.DateTimeField(auto_now_add=True)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-received_at"]

    def __str__(self) -> str:
        return f"{self.type} {self.event_id}"
