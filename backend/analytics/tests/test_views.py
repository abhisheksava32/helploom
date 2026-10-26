"""The Analytics endpoints in docs/API.md: roles, date range parameters and pagination."""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, Role
from analytics.tests.conftest import Seed
from core.testing import access_token_for

RANGE = "date_from=2026-10-01&date_to=2026-10-03"


@pytest.fixture
def agent_client(
    seed: Seed, make_member: Callable[..., Membership], client_for: Callable[..., APIClient]
) -> APIClient:
    return client_for(make_member(organization=seed.organization, role=Role.AGENT))


@pytest.mark.django_db
@pytest.mark.parametrize(
    "path", ["overview", "conversations-per-day", "top-questions", "top-documents", "unanswered", "costs"]
)
def test_every_report_answers_agents(agent_client: APIClient, path: str) -> None:
    response = agent_client.get(f"/api/v1/analytics/{path}/?{RANGE}")

    assert response.status_code == 200


@pytest.mark.django_db
def test_reports_need_a_member_of_that_organization(
    api_client: APIClient, owner: Membership, seed: Seed
) -> None:
    outsider = APIClient()
    outsider.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(owner.user)}",
        HTTP_X_ORGANIZATION_ID=str(seed.organization.id),
    )

    anonymous = api_client.get("/api/v1/analytics/overview/")
    foreign = outsider.get("/api/v1/analytics/overview/")

    assert anonymous.status_code == 401
    assert foreign.status_code == 403
    assert foreign.json()["error"]["code"] == "not_a_member"


@pytest.mark.django_db
def test_default_range_is_the_last_30_days(agent_client: APIClient) -> None:
    body = agent_client.get("/api/v1/analytics/conversations-per-day/").json()

    today = timezone.now().astimezone(dt.UTC).date()
    assert body["date_to"] == today.isoformat()
    assert body["date_from"] == (today - dt.timedelta(days=29)).isoformat()
    assert len(body["results"]) == 30


@pytest.mark.django_db
@pytest.mark.parametrize(
    "query",
    [
        "date_from=2026-10-05&date_to=2026-10-01",
        "date_from=2025-01-01&date_to=2026-10-01",
        "date_from=yesterday",
        "channel=email",
        "limit=0",
        "limit=51",
    ],
)
def test_invalid_parameters_are_validation_errors(agent_client: APIClient, query: str) -> None:
    response = agent_client.get(f"/api/v1/analytics/top-questions/?{query}")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


@pytest.mark.django_db
def test_overview_and_channel_filter(agent_client: APIClient) -> None:
    everything = agent_client.get(f"/api/v1/analytics/overview/?{RANGE}").json()
    widget = agent_client.get(f"/api/v1/analytics/overview/?{RANGE}&channel=widget").json()

    assert everything["questions"] == 4
    assert widget["questions"] == 3


@pytest.mark.django_db
def test_unanswered_is_paginated(agent_client: APIClient, seed: Seed) -> None:
    body: dict[str, Any] = agent_client.get(f"/api/v1/analytics/unanswered/?{RANGE}&page_size=1").json()

    assert body["count"] == 1
    assert body["next"] is None
    assert body["results"] == [
        {
            "message_id": str(seed.iceland_question.id),
            "conversation_id": str(seed.iceland_question.conversation_id),
            "question": "Do you ship to Iceland?",
            "channel": "playground",
            "asked_at": "2026-10-02T11:00:00Z",
            "top_similarity": 0.12,
            "has_ticket": True,
        }
    ]


@pytest.mark.django_db
def test_top_lists_respect_the_limit(agent_client: APIClient) -> None:
    questions = agent_client.get(f"/api/v1/analytics/top-questions/?{RANGE}&limit=2").json()
    documents = agent_client.get(f"/api/v1/analytics/top-documents/?{RANGE}&limit=1").json()
    costs = agent_client.get(f"/api/v1/analytics/costs/?{RANGE}").json()

    assert len(questions["results"]) == 2
    assert questions["results"][0]["count"] == 2
    assert documents["results"][0]["title"] == "Refund policy"
    assert costs["total_cost_usd"] == "0.004120"
