"""Usage metering and plan enforcement. Other apps call these before doing billable work:

    ensure_document_quota(org)            # knowledge, before accepting uploads
    ensure_seat_quota(org)                # accounts, before inviting
    consume_message_quota(org.id)         # assistant, before answering a question

Each raises core.exceptions.PlanLimitExceeded with a friendly message.
"""

from __future__ import annotations

import datetime as dt
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from core.exceptions import PlanLimitExceeded

from .models import Subscription, UsageCounter
from .plans import Plan, get_plan

if TYPE_CHECKING:
    from accounts.models import Organization


def current_period_start(now: dt.datetime | None = None) -> dt.date:
    now = now or timezone.now()
    return now.astimezone(dt.UTC).date().replace(day=1)


def get_subscription(organization_id: UUID | str) -> Subscription:
    subscription, _ = Subscription.objects.get_or_create(organization_id=organization_id)
    return subscription


def get_org_plan(organization_id: UUID | str) -> Plan:
    return get_plan(get_subscription(organization_id).plan)


def messages_used(organization_id: UUID | str) -> int:
    counter = UsageCounter.objects.filter(
        organization_id=organization_id, period_start=current_period_start()
    ).first()
    return counter.messages if counter else 0


def documents_used(organization_id: UUID | str) -> int:
    from knowledge.models import Document

    return Document.objects.filter(organization_id=organization_id).count()


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
        "messages": {"used": messages_used(organization_id), "limit": plan.messages_per_month},
        "documents": {"used": documents_used(organization_id), "limit": plan.documents},
        "seats": {"used": seats_used(organization_id), "limit": plan.seats},
        "period_start": current_period_start().isoformat(),
    }


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
    """Atomically count one answered question, refusing once the monthly limit is hit.

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
