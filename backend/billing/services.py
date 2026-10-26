"""Plans, usage metering, limits and plan changes.

Other apps call these before doing billable work (signatures fixed in docs/DESIGN.md):

    ensure_document_quota(org, adding=n)  # knowledge, before accepting uploads
    ensure_seat_quota(org, adding=1)      # accounts, before inviting
    consume_message_quota(org.id)         # assistant, once per question, before retrieval
    usage_snapshot(org.id)                # the UsageSummary dict

Each limit check raises core.exceptions.PlanLimitExceeded with a friendly message.

Billing runs in one of two modes. Without STRIPE_SECRET_KEY it is a demo: checkout
switches the plan at once. With a key, Checkout handles upgrades, the Customer Portal
handles changes and cancellation, and webhooks are the source of truth.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.exceptions import Conflict, PlanLimitExceeded, ServiceUnavailable
from core.realtime import broadcast_org_event

from . import stripe_client
from .models import BillingProvider, PlanCode, StripeEvent, Subscription, SubscriptionStatus, UsageCounter
from .plans import PLANS, Plan, get_plan

if TYPE_CHECKING:
    from accounts.models import Organization

logger = logging.getLogger(__name__)


def billing_mode() -> str:
    # Read at call time, not import time, so the mode follows the live settings.
    return "stripe" if stripe_client.is_configured() else "demo"


def list_plans() -> list[Plan]:
    return sorted(PLANS.values(), key=lambda plan: plan.price_monthly_cents)


# Subscriptions


def create_subscription(organization: Organization) -> Subscription:
    """Every organisation starts on Free, managed by the demo provider."""
    subscription, _ = Subscription.objects.get_or_create(organization=organization)
    return subscription


def get_subscription(organization_id: UUID | str) -> Subscription:
    subscription, _ = Subscription.objects.get_or_create(organization_id=organization_id)
    return subscription


def get_org_plan(organization_id: UUID | str) -> Plan:
    return get_plan(get_subscription(organization_id).plan)


def subscription_payload(subscription: Subscription) -> dict[str, Any]:
    from .serializers import SubscriptionSerializer

    return dict(SubscriptionSerializer(subscription).data)


def _publish_after_commit(subscription: Subscription) -> None:
    organization_id = subscription.organization_id

    def publish() -> None:
        fresh = Subscription.objects.get(pk=subscription.pk)
        broadcast_org_event(
            organization_id, {"type": "subscription.updated", "subscription": subscription_payload(fresh)}
        )

    transaction.on_commit(publish)


# Usage


def current_period_start(now: dt.datetime | None = None) -> dt.date:
    now = now or timezone.now()
    return now.astimezone(dt.UTC).date().replace(day=1)


def messages_used(organization_id: UUID | str) -> int:
    counter = UsageCounter.objects.filter(
        organization_id=organization_id, period_start=current_period_start()
    ).first()
    return counter.messages if counter else 0


def documents_used(organization_id: UUID | str) -> int:
    # Looked up lazily: billing should not import the knowledge app at module load.
    document = apps.get_model("knowledge", "Document")
    return int(document.objects.filter(organization_id=organization_id).count())


def seats_used(organization_id: UUID | str) -> int:
    """Members plus pending invitations, so invites cannot overshoot the plan."""
    from accounts.models import Invitation, Membership

    members = Membership.objects.filter(organization_id=organization_id).count()
    pending = Invitation.objects.filter(
        organization_id=organization_id,
        accepted_at__isnull=True,
        revoked_at__isnull=True,
        expires_at__gt=timezone.now(),
    ).count()
    return members + pending


def usage_snapshot(organization_id: UUID | str) -> dict[str, Any]:
    plan = get_org_plan(organization_id)
    return {
        "period_start": current_period_start().isoformat(),
        "messages": {"used": messages_used(organization_id), "limit": plan.messages_per_month},
        "documents": {"used": documents_used(organization_id), "limit": plan.documents},
        "seats": {"used": seats_used(organization_id), "limit": plan.seats},
    }


# Limits


def ensure_document_quota(organization: Organization, adding: int = 1) -> None:
    plan = get_org_plan(organization.id)
    used = documents_used(organization.id)
    if used + adding > plan.documents:
        raise PlanLimitExceeded(
            f"The {plan.name} plan holds up to {plan.documents} documents. "
            "Delete some documents or upgrade your plan to add more.",
            limit="documents",
            used=used,
            allowed=plan.documents,
            plan=plan.code,
        )


def ensure_seat_quota(organization: Organization, adding: int = 1) -> None:
    plan = get_org_plan(organization.id)
    used = seats_used(organization.id)
    if used + adding > plan.seats:
        raise PlanLimitExceeded(
            f"The {plan.name} plan includes {plan.seats} seats. Upgrade to invite more teammates.",
            limit="seats",
            used=used,
            allowed=plan.seats,
            plan=plan.code,
        )


def consume_message_quota(organization_id: UUID | str) -> None:
    """Atomically count one question, refusing once the monthly limit is hit.

    The conditional UPDATE makes the check and the increment one statement, so two
    concurrent requests cannot both squeeze past the last remaining message.
    """
    plan = get_org_plan(organization_id)
    period = current_period_start()
    with transaction.atomic():
        counter, _ = UsageCounter.objects.get_or_create(organization_id=organization_id, period_start=period)
        updated = UsageCounter.objects.filter(pk=counter.pk, messages__lt=plan.messages_per_month).update(
            messages=F("messages") + 1, updated_at=timezone.now()
        )
    if not updated:
        raise PlanLimitExceeded(
            f"This workspace has used all {plan.messages_per_month} answers included in the "
            f"{plan.name} plan this month. Upgrade the plan or try again next month.",
            limit="messages",
            used=plan.messages_per_month,
            allowed=plan.messages_per_month,
            plan=plan.code,
        )


# Plan changes


def downgrade_blocker(organization_id: UUID | str, target: Plan) -> dict[str, Any] | None:
    """The first live limit the organisation already exceeds on the target plan.

    Monthly messages are not checked: they reset on the 1st, and an organisation over
    the new allowance simply cannot ask more questions until then.
    """
    for limit, used, allowed in (
        ("documents", documents_used(organization_id), target.documents),
        ("seats", seats_used(organization_id), target.seats),
    ):
        if used > allowed:
            return {"limit": limit, "used": used, "allowed": allowed}
    return None


@dataclass(frozen=True)
class CheckoutResult:
    mode: str
    checkout_url: str | None
    subscription: Subscription


def _validate_plan_change(subscription: Subscription, target: Plan) -> None:
    if subscription.plan == target.code:
        raise Conflict(f"You are already on the {target.name} plan.", code="plan_unchanged")
    blocker = downgrade_blocker(subscription.organization_id, target)
    if blocker is not None:
        raise Conflict(
            f"This workspace uses {blocker['used']} {blocker['limit']}, more than the {target.name} plan "
            f"allows ({blocker['allowed']}). Remove some before switching.",
            code="plan_downgrade_blocked",
            details=blocker,
        )


def apply_plan(subscription: Subscription, plan_code: str) -> Subscription:
    """Switch the plan immediately. Demo mode, and Stripe mode moves that need no payment."""
    subscription.plan = plan_code
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.cancel_at_period_end = False
    subscription.save(update_fields=["plan", "status", "cancel_at_period_end", "updated_at"])
    _publish_after_commit(subscription)
    return subscription


def billing_return_url(outcome: str | None = None) -> str:
    url = f"{settings.FRONTEND_URL}/app/settings/billing"
    return f"{url}?checkout={outcome}" if outcome else url


def start_checkout(organization: Organization, plan_code: str, *, customer_email: str = "") -> CheckoutResult:
    target = PLANS[plan_code]
    with transaction.atomic():
        subscription = Subscription.objects.select_for_update().get(pk=get_subscription(organization.id).pk)
        _validate_plan_change(subscription, target)

        if billing_mode() == "demo":
            return CheckoutResult("demo", None, apply_plan(subscription, target.code))

        if subscription.stripe_subscription_id:
            raise Conflict(
                "Change or cancel your paid plan in the billing portal.", code="use_billing_portal"
            )
        if target.code == PlanCode.FREE:
            # Nothing to pay and no Stripe subscription to cancel.
            return CheckoutResult("stripe", None, apply_plan(subscription, target.code))
        if not target.stripe_price_id:
            logger.error("No Stripe price configured for the %s plan", target.code)
            raise ServiceUnavailable("This plan cannot be bought right now. Please contact support.")

    url = stripe_client.create_checkout_session(
        organization_id=str(organization.id),
        plan_code=target.code,
        price_id=target.stripe_price_id,
        customer_id=subscription.stripe_customer_id,
        customer_email=customer_email,
        success_url=billing_return_url("success"),
        cancel_url=billing_return_url("cancelled"),
    )
    # The plan changes when Stripe confirms payment through the webhook.
    return CheckoutResult("stripe", url, subscription)


def billing_portal_url(organization: Organization) -> str:
    subscription = get_subscription(organization.id)
    if billing_mode() != "stripe" or not subscription.stripe_customer_id:
        raise Conflict(
            "The billing portal is available once you have a paid Stripe subscription.",
            code="billing_portal_unavailable",
        )
    return stripe_client.create_portal_session(
        customer_id=subscription.stripe_customer_id, return_url=billing_return_url()
    )


# Stripe webhooks

_STRIPE_STATUS = {
    "active": SubscriptionStatus.ACTIVE,
    "trialing": SubscriptionStatus.TRIALING,
    "past_due": SubscriptionStatus.PAST_DUE,
    "unpaid": SubscriptionStatus.PAST_DUE,
    "paused": SubscriptionStatus.PAST_DUE,
    "incomplete": SubscriptionStatus.INCOMPLETE,
    "incomplete_expired": SubscriptionStatus.CANCELED,
    "canceled": SubscriptionStatus.CANCELED,
}


def handle_stripe_webhook(payload: bytes, signature: str | None) -> None:
    """Verify, record and apply one event. Each event id is applied once: a retried
    delivery finds the event already processed and does nothing. A failure rolls the
    record back too, so Stripe's retry gets another chance."""
    event = stripe_client.verify_webhook(payload, signature)
    with transaction.atomic():
        record, _ = StripeEvent.objects.select_for_update().get_or_create(
            event_id=event["id"], defaults={"type": str(event.get("type", "")), "payload": event}
        )
        if record.processed_at is not None:
            return
        _apply_event(event)
        record.processed_at = timezone.now()
        record.save(update_fields=["processed_at"])


def _apply_event(event: dict[str, Any]) -> None:
    kind = event.get("type")
    obj = (event.get("data") or {}).get("object") or {}
    if kind == "checkout.session.completed":
        _on_checkout_completed(obj)
    elif kind in ("customer.subscription.created", "customer.subscription.updated"):
        _on_subscription_changed(obj)
    elif kind == "customer.subscription.deleted":
        _on_subscription_deleted(obj)
    elif kind == "invoice.payment_failed":
        _on_payment_failed(obj)


def _id(value: Any) -> str:
    """Stripe sends either an id string or an expanded object for references."""
    if isinstance(value, dict):
        return str(value.get("id") or "")
    return str(value or "")


def _find_subscription(
    *, organization_id: Any = None, stripe_subscription_id: str = "", customer_id: str = ""
) -> Subscription | None:
    queryset = Subscription.objects.select_for_update()
    if stripe_subscription_id:
        found = queryset.filter(stripe_subscription_id=stripe_subscription_id).first()
        if found is not None:
            return found
    if organization_id:
        try:
            found = queryset.filter(organization_id=UUID(str(organization_id))).first()
        except ValueError:
            found = None
        if found is not None:
            return found
    if customer_id:
        return queryset.filter(stripe_customer_id=customer_id).first()
    return None


def _plan_for_price(price_id: str, fallback: str) -> str:
    for plan in PLANS.values():
        if price_id and plan.stripe_price_id == price_id:
            return plan.code
    return fallback if fallback in PLANS else PlanCode.FREE


def _timestamp(value: Any) -> dt.datetime | None:
    if isinstance(value, int | float):
        return dt.datetime.fromtimestamp(value, tz=dt.UTC)
    return None


def _on_checkout_completed(session: dict[str, Any]) -> None:
    metadata = session.get("metadata") or {}
    subscription = _find_subscription(
        organization_id=session.get("client_reference_id") or metadata.get("organization_id"),
        customer_id=_id(session.get("customer")),
    )
    if subscription is None:
        logger.warning("Checkout completed for an unknown organisation")
        return
    plan = metadata.get("plan")
    subscription.provider = BillingProvider.STRIPE
    subscription.stripe_customer_id = _id(session.get("customer")) or subscription.stripe_customer_id
    subscription.stripe_subscription_id = (
        _id(session.get("subscription")) or subscription.stripe_subscription_id
    )
    if plan in PLANS:
        subscription.plan = plan
    subscription.status = SubscriptionStatus.ACTIVE
    subscription.save()
    _publish_after_commit(subscription)


def _on_subscription_changed(stripe_sub: dict[str, Any]) -> None:
    metadata = stripe_sub.get("metadata") or {}
    subscription = _find_subscription(
        stripe_subscription_id=_id(stripe_sub.get("id")),
        organization_id=metadata.get("organization_id"),
        customer_id=_id(stripe_sub.get("customer")),
    )
    if subscription is None:
        logger.warning("Subscription event for an unknown organisation")
        return
    items = ((stripe_sub.get("items") or {}).get("data")) or [{}]
    first_item = items[0] or {}
    price_id = _id((first_item.get("price") or {}).get("id"))
    status = _STRIPE_STATUS.get(str(stripe_sub.get("status")), SubscriptionStatus.INCOMPLETE)

    subscription.provider = BillingProvider.STRIPE
    subscription.stripe_customer_id = _id(stripe_sub.get("customer")) or subscription.stripe_customer_id
    subscription.stripe_subscription_id = _id(stripe_sub.get("id"))
    subscription.status = status
    subscription.plan = (
        PlanCode.FREE
        if status == SubscriptionStatus.CANCELED
        else _plan_for_price(price_id, str(metadata.get("plan") or subscription.plan))
    )
    # Newer API versions report the billing period per subscription item.
    subscription.current_period_start = _timestamp(
        stripe_sub.get("current_period_start", first_item.get("current_period_start"))
    )
    subscription.current_period_end = _timestamp(
        stripe_sub.get("current_period_end", first_item.get("current_period_end"))
    )
    subscription.cancel_at_period_end = bool(stripe_sub.get("cancel_at_period_end"))
    subscription.save()
    _publish_after_commit(subscription)


def _on_subscription_deleted(stripe_sub: dict[str, Any]) -> None:
    subscription = _find_subscription(
        stripe_subscription_id=_id(stripe_sub.get("id")), customer_id=_id(stripe_sub.get("customer"))
    )
    if subscription is None:
        return
    # Back to Free. The customer id stays so a later upgrade reuses the same customer.
    subscription.plan = PlanCode.FREE
    subscription.status = SubscriptionStatus.CANCELED
    subscription.stripe_subscription_id = ""
    subscription.current_period_start = None
    subscription.current_period_end = None
    subscription.cancel_at_period_end = False
    subscription.save()
    _publish_after_commit(subscription)


def _on_payment_failed(invoice: dict[str, Any]) -> None:
    parent = (invoice.get("parent") or {}).get("subscription_details") or {}
    subscription = _find_subscription(
        stripe_subscription_id=_id(invoice.get("subscription") or parent.get("subscription")),
        customer_id=_id(invoice.get("customer")),
    )
    if subscription is None:
        return
    # The plan stays while Stripe retries the payment; the UI asks for a new card.
    subscription.status = SubscriptionStatus.PAST_DUE
    subscription.save(update_fields=["status", "updated_at"])
    _publish_after_commit(subscription)
