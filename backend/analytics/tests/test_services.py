"""Every report query against the seeded history in conftest.py, including channel
filtering and tenant isolation."""

from __future__ import annotations

import datetime as dt

import pytest

from analytics import services
from analytics.services import ReportRange
from analytics.tests.conftest import Seed, at

OCTOBER = ReportRange(dt.date(2026, 10, 1), dt.date(2026, 10, 3))
WIDGET_ONLY = ReportRange(dt.date(2026, 10, 1), dt.date(2026, 10, 3), channel="widget")


@pytest.mark.django_db
def test_overview(seed: Seed) -> None:
    assert services.overview(seed.organization, OCTOBER) == {
        "date_from": "2026-10-01",
        "date_to": "2026-10-03",
        "conversations": 3,
        "questions": 4,
        "answered": 2,
        "not_found": 1,
        "refused": 0,
        "errors": 1,
        "answer_rate": 0.5,
        "not_found_rate": 0.25,
        "ratings": {"up": 1, "down": 1, "average": 0.0, "satisfaction": 0.5},
        "avg_latency_ms": 2000,
        "avg_first_token_ms": 300,
        "tickets_opened": 1,
        "cost_usd": "0.004120",
    }


@pytest.mark.django_db
def test_overview_for_one_channel(seed: Seed) -> None:
    report = services.overview(seed.organization, WIDGET_ONLY)

    assert (report["conversations"], report["questions"], report["not_found"]) == (2, 3, 0)
    assert report["tickets_opened"] == 0


@pytest.mark.django_db
def test_an_empty_range_has_zero_rates_and_null_averages(seed: Seed) -> None:
    report = services.overview(seed.organization, ReportRange(dt.date(2026, 8, 1), dt.date(2026, 8, 2)))

    assert report["questions"] == 0
    assert report["answer_rate"] == 0
    assert report["ratings"] == {"up": 0, "down": 0, "average": None, "satisfaction": None}
    assert report["avg_latency_ms"] is None
    assert report["cost_usd"] == "0.000000"


@pytest.mark.django_db
def test_conversations_per_day_fills_every_day(seed: Seed) -> None:
    report = services.conversations_per_day(
        seed.organization, ReportRange(dt.date(2026, 10, 1), dt.date(2026, 10, 4))
    )

    assert report["results"] == [
        {"date": "2026-10-01", "conversations": 1, "questions": 1, "answered": 1, "not_found": 0},
        {"date": "2026-10-02", "conversations": 1, "questions": 2, "answered": 1, "not_found": 1},
        {"date": "2026-10-03", "conversations": 1, "questions": 1, "answered": 0, "not_found": 0},
        {"date": "2026-10-04", "conversations": 0, "questions": 0, "answered": 0, "not_found": 0},
    ]


@pytest.mark.django_db
def test_top_questions_group_by_normalised_text(seed: Seed) -> None:
    results = services.top_questions(seed.organization, OCTOBER, limit=10)

    assert results[0] == {
        "question": "how long do refunds take",  # the most recent wording
        "count": 2,
        "answered": 2,
        "not_found": 0,
        "last_asked_at": at(2, 10),
    }
    assert [row["question"] for row in results[1:]] == ["Where is my order?", "Do you ship to Iceland?"]
    assert results[2]["not_found"] == 1
    assert len(services.top_questions(seed.organization, OCTOBER, limit=1)) == 1


@pytest.mark.django_db
def test_top_documents_include_deleted_ones_by_title(seed: Seed) -> None:
    assert services.top_documents(seed.organization, OCTOBER, limit=10) == [
        {"document_id": seed.refund_doc.id, "title": "Refund policy", "citations": 2, "answers": 2},
        {"document_id": None, "title": "Old policy", "citations": 1, "answers": 1},
        {"document_id": seed.shipping_doc.id, "title": "Shipping guide", "citations": 1, "answers": 1},
    ]


@pytest.mark.django_db
def test_unanswered_questions_list_content_gaps(seed: Seed) -> None:
    rows = list(services.unanswered_questions(seed.organization, OCTOBER))

    assert len(rows) == 1
    row = rows[0]
    assert row.id == seed.iceland_question.id
    assert row.content == "Do you ship to Iceland?"
    assert (row.channel, row.top_similarity, row.has_ticket) == ("playground", 0.12, True)
    assert list(services.unanswered_questions(seed.organization, WIDGET_ONLY)) == []


@pytest.mark.django_db
def test_costs_by_provider_and_model(seed: Seed) -> None:
    report = services.costs(seed.organization, OCTOBER)

    assert report["results"][0] == {
        "provider": "claude",
        "model": "claude-opus-5-5",
        "messages": 1,
        "input_tokens": 1000,
        "output_tokens": 100,
        "cache_read_input_tokens": 500,
        "cache_creation_input_tokens": 0,
        "cost_usd": "0.004120",
    }
    assert [(row["provider"], row["cost_usd"]) for row in report["results"][1:]] == [
        ("extractive", "0.000000"),
        ("ollama", "0.000000"),
    ]
    assert report["total_cost_usd"] == "0.004120"


@pytest.mark.django_db
def test_other_organizations_never_leak_in(seed: Seed) -> None:
    assert services.overview(seed.other, OCTOBER)["questions"] == 1
    assert services.overview(seed.other, OCTOBER)["cost_usd"] == "9.000000"
    assert services.top_documents(seed.other, OCTOBER, limit=10) == []
    for report in (services.overview(seed.organization, OCTOBER), services.costs(seed.organization, OCTOBER)):
        assert "9.000000" not in str(report)
