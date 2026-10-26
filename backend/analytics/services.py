"""Report queries over the assistant app's tables (docs/API.md, section 12).

The models are looked up with apps.get_model rather than imported, so analytics
depends only on the field names in docs/DESIGN.md, not on the assistant package.
Every query filters by organisation first and by created_at as a half open UTC range
[date_from 00:00, date_to + 1 day 00:00), which the (organization, created_at)
indexes on Message serve directly.

"Questions" are user messages and "answers" are assistant messages. Rates are
rounded to 4 places and money is a string with 6 decimal places.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.apps import apps
from django.db.models import (
    Avg,
    Count,
    Exists,
    F,
    Max,
    OuterRef,
    Q,
    QuerySet,
    Subquery,
    Sum,
    Value,
)
from django.db.models.functions import Coalesce, Lower, NullIf, Substr, TruncDate

MONEY = Decimal("0.000001")


@dataclass(frozen=True)
class ReportRange:
    date_from: dt.date
    date_to: dt.date
    channel: str | None = None

    @property
    def start(self) -> dt.datetime:
        return dt.datetime.combine(self.date_from, dt.time.min, tzinfo=dt.UTC)

    @property
    def end(self) -> dt.datetime:
        return dt.datetime.combine(self.date_to + dt.timedelta(days=1), dt.time.min, tzinfo=dt.UTC)

    def days(self) -> list[dt.date]:
        count = (self.date_to - self.date_from).days + 1
        return [self.date_from + dt.timedelta(days=offset) for offset in range(count)]


def _model(name: str) -> Any:
    return apps.get_model("assistant", name)


def _org_id(organization: Any) -> Any:
    return getattr(organization, "pk", organization)


def money(value: Decimal | int | float | None) -> str:
    return str(Decimal(value or 0).quantize(MONEY))


def _rate(part: int, whole: int) -> float:
    return round(part / whole, 4) if whole else 0


def conversations(organization: Any, report: ReportRange) -> QuerySet[Any]:
    queryset = _model("Conversation").objects.filter(
        organization_id=_org_id(organization), created_at__gte=report.start, created_at__lt=report.end
    )
    if report.channel:
        queryset = queryset.filter(channel=report.channel)
    return queryset


def messages(organization: Any, report: ReportRange, role: str) -> QuerySet[Any]:
    queryset = _model("Message").objects.filter(
        organization_id=_org_id(organization),
        role=role,
        created_at__gte=report.start,
        created_at__lt=report.end,
    )
    if report.channel:
        queryset = queryset.filter(conversation__channel=report.channel)
    return queryset


def questions(organization: Any, report: ReportRange) -> QuerySet[Any]:
    return messages(organization, report, "user")


def answers(organization: Any, report: ReportRange) -> QuerySet[Any]:
    return messages(organization, report, "assistant")


def overview(organization: Any, report: ReportRange) -> dict[str, Any]:
    by_type = answers(organization, report).aggregate(
        answered=Count("id", filter=Q(answer_type="answered")),
        not_found=Count("id", filter=Q(answer_type="not_found")),
        refused=Count("id", filter=Q(answer_type="refused")),
        errors=Count("id", filter=Q(answer_type="error")),
        up=Count("id", filter=Q(rating=1)),
        down=Count("id", filter=Q(rating=-1)),
        rating_avg=Avg("rating"),
        latency=Avg("latency_ms", filter=Q(answer_type="answered")),
        first_token=Avg("first_token_ms", filter=Q(answer_type="answered")),
        cost=Sum("cost_usd"),
    )
    question_count = questions(organization, report).count()
    up, down = by_type["up"], by_type["down"]

    tickets = _model("HandoffTicket").objects.filter(
        organization_id=_org_id(organization), created_at__gte=report.start, created_at__lt=report.end
    )
    if report.channel:
        tickets = tickets.filter(conversation__channel=report.channel)

    return {
        "date_from": report.date_from.isoformat(),
        "date_to": report.date_to.isoformat(),
        "conversations": conversations(organization, report).count(),
        "questions": question_count,
        "answered": by_type["answered"],
        "not_found": by_type["not_found"],
        "refused": by_type["refused"],
        "errors": by_type["errors"],
        "answer_rate": _rate(by_type["answered"], question_count),
        "not_found_rate": _rate(by_type["not_found"], question_count),
        "ratings": {
            "up": up,
            "down": down,
            "average": round(float(by_type["rating_avg"]), 4) if up + down else None,
            "satisfaction": _rate(up, up + down) if up + down else None,
        },
        "avg_latency_ms": round(by_type["latency"]) if by_type["latency"] is not None else None,
        "avg_first_token_ms": round(by_type["first_token"]) if by_type["first_token"] is not None else None,
        "tickets_opened": tickets.count(),
        "cost_usd": money(by_type["cost"]),
    }


def conversations_per_day(organization: Any, report: ReportRange) -> dict[str, Any]:
    def per_day(queryset: QuerySet[Any], **counts: Any) -> dict[dt.date, dict[str, int]]:
        rows = queryset.annotate(day=TruncDate("created_at", tzinfo=dt.UTC)).values("day").annotate(**counts)
        return {row["day"]: row for row in rows}

    conversation_rows = per_day(conversations(organization, report), conversations=Count("id"))
    question_rows = per_day(questions(organization, report), questions=Count("id"))
    answer_rows = per_day(
        answers(organization, report),
        answered=Count("id", filter=Q(answer_type="answered")),
        not_found=Count("id", filter=Q(answer_type="not_found")),
    )

    results = []
    for day in report.days():
        answered = answer_rows.get(day, {})
        results.append(
            {
                "date": day.isoformat(),
                "conversations": conversation_rows.get(day, {}).get("conversations", 0),
                "questions": question_rows.get(day, {}).get("questions", 0),
                "answered": answered.get("answered", 0),
                "not_found": answered.get("not_found", 0),
            }
        )
    return {
        "date_from": report.date_from.isoformat(),
        "date_to": report.date_to.isoformat(),
        "results": results,
    }


def _question_key() -> Any:
    # normalized_content is what the pipeline groups by; the fallback keeps a question
    # countable if it was stored without one.
    return Coalesce(NullIf(F("normalized_content"), Value("")), Lower(Substr("content", 1, 300)))


def top_questions(organization: Any, report: ReportRange, limit: int) -> list[dict[str, Any]]:
    base = questions(organization, report).annotate(question_key=_question_key())
    groups = list(
        base.values("question_key")
        .annotate(
            count=Count("id", distinct=True),
            answered=Count("id", filter=Q(replies__answer_type="answered"), distinct=True),
            not_found=Count("id", filter=Q(replies__answer_type="not_found"), distinct=True),
            last_asked_at=Max("created_at"),
        )
        .order_by("-count", "-last_asked_at", "question_key")[:limit]
    )
    # Second query, DISTINCT ON: the most recent original wording of each group. A
    # correlated subquery on the grouped expression is not allowed by PostgreSQL.
    wording = dict(
        base.filter(question_key__in=[group["question_key"] for group in groups])
        .order_by("question_key", "-created_at")
        .distinct("question_key")
        .values_list("question_key", "content")
    )
    return [
        {
            "question": wording.get(group["question_key"], group["question_key"]),
            "count": group["count"],
            "answered": group["answered"],
            "not_found": group["not_found"],
            "last_asked_at": group["last_asked_at"],
        }
        for group in groups
    ]


def top_documents(organization: Any, report: ReportRange, limit: int) -> list[dict[str, Any]]:
    citations = _model("Citation").objects.filter(
        message__organization_id=_org_id(organization),
        message__created_at__gte=report.start,
        message__created_at__lt=report.end,
    )
    if report.channel:
        citations = citations.filter(message__conversation__channel=report.channel)
    rows = (
        # Live documents group by id under their current title; deleted ones (id now
        # null) group by the title copied onto the citation.
        citations.annotate(title=Coalesce("document__title", "document_title"))
        .values("document_id", "title")
        .annotate(citation_count=Count("id"), answers=Count("message_id", distinct=True))
        .order_by("-citation_count", "-answers", "title")[:limit]
    )
    return [
        {
            "document_id": row["document_id"],
            "title": row["title"],
            "citations": row["citation_count"],
            "answers": row["answers"],
        }
        for row in rows
    ]


def unanswered_questions(organization: Any, report: ReportRange) -> QuerySet[Any]:
    """User messages whose reply was not_found, newest first (the content gap list)."""
    message_model = _model("Message")
    not_found_reply = message_model.objects.filter(reply_to=OuterRef("pk"), answer_type="not_found")
    return (
        questions(organization, report)
        .filter(Exists(not_found_reply))
        .annotate(
            channel=F("conversation__channel"),
            top_similarity=Subquery(not_found_reply.order_by("-created_at").values("top_score")[:1]),
            has_ticket=Exists(
                _model("HandoffTicket").objects.filter(conversation=OuterRef("conversation_id"))
            ),
        )
        .order_by("-created_at", "-pk")
    )


def costs(organization: Any, report: ReportRange) -> dict[str, Any]:
    rows = (
        answers(organization, report)
        .exclude(provider="")
        .values("provider", "model")
        .annotate(
            messages=Count("id"),
            input_tokens=Coalesce(Sum("input_tokens"), 0),
            output_tokens=Coalesce(Sum("output_tokens"), 0),
            cache_read_input_tokens=Coalesce(Sum("cache_read_input_tokens"), 0),
            cache_creation_input_tokens=Coalesce(Sum("cache_creation_input_tokens"), 0),
            cost=Sum("cost_usd"),
        )
        .order_by("-cost", "-messages", "provider", "model")
    )
    results = []
    total = Decimal(0)
    for row in rows:
        cost = Decimal(row.pop("cost") or 0)
        total += cost
        results.append({**row, "cost_usd": money(cost)})
    return {
        "date_from": report.date_from.isoformat(),
        "date_to": report.date_to.isoformat(),
        "results": results,
        "total_cost_usd": money(total),
    }
