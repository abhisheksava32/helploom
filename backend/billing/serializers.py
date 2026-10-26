"""Plans, the subscription with its usage, and checkout input. Field names follow
docs/API.md ("Plan", "UsageSummary", "Subscription", section 11)."""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from . import services
from .models import Subscription
from .plans import PLANS, Plan, get_plan


class PlanSerializer(serializers.Serializer):
    code = serializers.CharField(read_only=True)
    name = serializers.CharField(read_only=True)
    price_monthly_cents = serializers.IntegerField(read_only=True)
    currency = serializers.SerializerMethodField()
    limits = serializers.SerializerMethodField()
    features = serializers.ListField(child=serializers.CharField(), read_only=True)

    def get_currency(self, plan: Plan) -> str:
        return "usd"

    def get_limits(self, plan: Plan) -> dict[str, int]:
        return {
            "messages_per_month": plan.messages_per_month,
            "documents": plan.documents,
            "seats": plan.seats,
        }


class SubscriptionSerializer(serializers.Serializer):
    plan = serializers.SerializerMethodField()
    status = serializers.CharField(read_only=True)
    provider = serializers.CharField(read_only=True)
    billing_mode = serializers.SerializerMethodField()
    current_period_start = serializers.DateTimeField(read_only=True, allow_null=True)
    current_period_end = serializers.DateTimeField(read_only=True, allow_null=True)
    cancel_at_period_end = serializers.BooleanField(read_only=True)
    usage = serializers.SerializerMethodField()

    def get_plan(self, subscription: Subscription) -> dict[str, Any]:
        return dict(PlanSerializer(get_plan(subscription.plan)).data)

    def get_billing_mode(self, subscription: Subscription) -> str:
        return services.billing_mode()

    def get_usage(self, subscription: Subscription) -> dict[str, Any]:
        return services.usage_snapshot(subscription.organization_id)


class CheckoutSerializer(serializers.Serializer):
    plan = serializers.ChoiceField(choices=list(PLANS))
