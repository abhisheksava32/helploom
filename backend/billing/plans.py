"""Plan catalogue. Plans live in code rather than the database: they change with
releases, are referenced by tests, and Stripe price ids come from the environment."""

from __future__ import annotations

from dataclasses import dataclass

from django.conf import settings


@dataclass(frozen=True)
class Plan:
    code: str
    name: str
    price_monthly_cents: int
    messages_per_month: int
    documents: int
    seats: int
    features: tuple[str, ...]

    @property
    def stripe_price_id(self) -> str:
        return {
            "starter": settings.STRIPE_PRICE_STARTER,
            "pro": settings.STRIPE_PRICE_PRO,
        }.get(self.code, "")


PLANS: dict[str, Plan] = {
    "free": Plan(
        code="free",
        name="Free",
        price_monthly_cents=0,
        messages_per_month=200,
        documents=10,
        seats=2,
        features=("Website widget", "Local and offline answer modes", "Basic reports"),
    ),
    "starter": Plan(
        code="starter",
        name="Starter",
        price_monthly_cents=2900,
        messages_per_month=3000,
        documents=100,
        seats=5,
        features=("Everything in Free", "Claude API answers", "Handoff tickets", "Full reports"),
    ),
    "pro": Plan(
        code="pro",
        name="Pro",
        price_monthly_cents=9900,
        messages_per_month=20000,
        documents=1000,
        seats=20,
        features=("Everything in Starter", "Priority ingestion", "Cost reporting by provider"),
    ),
}

DEFAULT_PLAN = "free"


def get_plan(code: str) -> Plan:
    return PLANS.get(code, PLANS[DEFAULT_PLAN])
