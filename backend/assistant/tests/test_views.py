"""The Conversations, Tickets and Assistant endpoints in docs/API.md."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import Membership, Organization, User
from assistant.models import Citation, Conversation, HandoffTicket, Message
from core.testing import access_token_for
from knowledge.models import Document

pytestmark = pytest.mark.django_db

SUMMARY_FIELDS = {
    "id", "channel", "status", "title", "message_count", "last_message_at", "created_at", "started_by",
    "visitor_id", "origin", "page_url", "last_answer_type", "providers", "thumbs_up", "thumbs_down",
    "open_tickets",
}  # fmt: skip
MESSAGE_FIELDS = {
    "id", "role", "content", "status", "answer_type", "reply_to", "provider", "model", "latency_ms",
    "first_token_ms", "usage", "cost_usd", "rating", "feedback_comment", "citations", "created_at",
}  # fmt: skip


def client_for(membership: Membership) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(membership.user)}",
        HTTP_X_ORGANIZATION_ID=str(membership.organization_id),
    )
    return client


@pytest.fixture
def agent(organization: Organization, make_member: Callable[..., Membership]) -> Membership:
    return make_member(organization=organization, role="agent")


@pytest.fixture
def agent_client(agent: Membership) -> APIClient:
    return client_for(agent)


def make_exchange(
    organization: Organization,
    *,
    channel: str = "widget",
    question: str = "How long do refunds take?",
    answer_type: str = "answered",
    provider: str = "extractive",
    rating: int | None = None,
    started_by: User | None = None,
) -> Conversation:
    conversation = Conversation.objects.create(
        organization=organization,
        channel=channel,
        title=question,
        visitor_id="v_visitor_00000000001" if channel == "widget" else "",
        started_by=started_by,
        message_count=2,
        last_message_at=timezone.now(),
    )
    user = Message.objects.create(
        organization=organization, conversation=conversation, role="user", content=question
    )
    answer = Message.objects.create(
        organization=organization,
        conversation=conversation,
        role="assistant",
        content="Within 5 business days [1].",
        answer_type=answer_type,
        provider=provider,
        model="extractive-v1",
        reply_to=user,
        rating=rating,
        latency_ms=12,
    )
    Citation.objects.create(
        message=answer, marker=1, document_title="Refund policy", snippet="5 business days"
    )
    return conversation


def test_conversation_list_summaries(
    agent_client: APIClient, organization: Organization, owner: Membership
) -> None:
    widget = make_exchange(organization, rating=1)
    make_exchange(organization, channel="playground", started_by=owner.user, answer_type="not_found")
    HandoffTicket.objects.create(
        organization=organization, conversation=widget, requester_email="jo@example.net"
    )

    body = agent_client.get("/api/v1/conversations/").json()

    assert body["count"] == 2
    summaries = {s["channel"]: s for s in body["results"]}
    assert set(summaries["widget"]) == SUMMARY_FIELDS
    assert summaries["widget"]["providers"] == ["extractive"]
    assert (summaries["widget"]["thumbs_up"], summaries["widget"]["thumbs_down"]) == (1, 0)
    assert summaries["widget"]["open_tickets"] == 1
    assert summaries["widget"]["started_by"] is None
    assert summaries["playground"]["started_by"]["email"] == owner.user.email
    assert summaries["playground"]["last_answer_type"] == "not_found"


@pytest.mark.parametrize(
    ("query", "expected"),
    [
        ("channel=widget", {"Widget refunds"}),
        ("answer_type=not_found", {"Gap question"}),
        ("rating=up", {"Widget refunds"}),
        ("rating=down", set()),
        ("provider=claude", {"Gap question"}),
        ("has_ticket=true", {"Widget refunds"}),
        ("has_ticket=false", {"Gap question"}),
        ("search=GAP", {"Gap question"}),
        ("search=business days", {"Widget refunds", "Gap question"}),
        ("status=handed_off", set()),
    ],
)
def test_conversation_filters(
    agent_client: APIClient, organization: Organization, query: str, expected: set[str]
) -> None:
    widget = make_exchange(organization, question="Widget refunds", rating=1)
    make_exchange(
        organization,
        channel="playground",
        question="Gap question",
        answer_type="not_found",
        provider="claude",
    )
    HandoffTicket.objects.create(
        organization=organization, conversation=widget, requester_email="jo@example.net"
    )

    body = agent_client.get(f"/api/v1/conversations/?{query}").json()

    assert {s["title"] for s in body["results"]} == expected


def test_conversation_date_filters_and_ordering(agent_client: APIClient, organization: Organization) -> None:
    old = make_exchange(organization, question="Old one")
    Conversation.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=10))
    make_exchange(organization, question="New one")
    today = timezone.now().date().isoformat()

    assert [
        s["title"] for s in agent_client.get(f"/api/v1/conversations/?date_from={today}").json()["results"]
    ] == ["New one"]
    titles = [
        s["title"] for s in agent_client.get("/api/v1/conversations/?ordering=created_at").json()["results"]
    ]
    assert titles == ["Old one", "New one"]
    bad = agent_client.get("/api/v1/conversations/?date_from=2026-02-02&date_to=2026-01-01")
    assert bad.status_code == 400


def test_conversation_detail_has_messages_citations_and_tickets(
    agent_client: APIClient, organization: Organization
) -> None:
    conversation = make_exchange(organization)
    HandoffTicket.objects.create(
        organization=organization, conversation=conversation, requester_email="jo@example.net"
    )

    body = agent_client.get(f"/api/v1/conversations/{conversation.id}/").json()

    assert [m["role"] for m in body["messages"]] == ["user", "assistant"]
    answer = body["messages"][1]
    assert set(answer) == MESSAGE_FIELDS
    assert answer["cost_usd"] == "0.000000"
    assert answer["reply_to"] == body["messages"][0]["id"]
    assert answer["citations"] == [
        {
            "marker": 1,
            "document_id": None,
            "chunk_id": None,
            "document_title": "Refund policy",
            "location": "",
            "snippet": "5 business days",
            "score": None,
        }
    ]
    assert body["tickets"][0]["requester_email"] == "jo@example.net"
    assert body["messages"][0]["usage"]["input_tokens"] == 0


def test_conversations_are_isolated(
    agent_client: APIClient, make_organization: Callable[..., Organization]
) -> None:
    theirs = make_exchange(make_organization())

    assert agent_client.get("/api/v1/conversations/").json()["count"] == 0
    assert agent_client.get(f"/api/v1/conversations/{theirs.id}/").status_code == 404
    assert agent_client.patch(f"/api/v1/conversations/{theirs.id}/", {"status": "closed"}).status_code == 404


def test_agents_can_close_conversations(agent_client: APIClient, organization: Organization) -> None:
    conversation = make_exchange(organization)

    response = agent_client.patch(f"/api/v1/conversations/{conversation.id}/", {"status": "closed"})

    assert response.status_code == 200
    assert response.json()["status"] == "closed"
    assert set(response.json()) == SUMMARY_FIELDS
    assert (
        agent_client.patch(f"/api/v1/conversations/{conversation.id}/", {"status": "nope"}).status_code == 400
    )


def test_feedback_from_the_dashboard(agent_client: APIClient, organization: Organization) -> None:
    conversation = make_exchange(organization)
    user, answer = conversation.messages.order_by("created_at")

    rated = agent_client.post(
        f"/api/v1/messages/{answer.id}/feedback/", {"rating": -1, "comment": "Wrong policy."}
    )
    assert rated.status_code == 200
    assert (rated.json()["rating"], rated.json()["feedback_comment"]) == (-1, "Wrong policy.")
    answer.refresh_from_db()
    assert answer.rated_at is not None

    cleared = agent_client.post(f"/api/v1/messages/{answer.id}/feedback/", {"rating": None}, format="json")
    assert cleared.json()["rating"] is None

    user_message = agent_client.post(f"/api/v1/messages/{user.id}/feedback/", {"rating": 1})
    assert user_message.status_code == 400
    assert user_message.json()["error"]["code"] == "validation_error"
    assert agent_client.post(f"/api/v1/messages/{answer.id}/feedback/", {"rating": 5}).status_code == 400


def test_feedback_on_another_organizations_message_is_404(
    agent_client: APIClient, make_organization: Callable[..., Organization]
) -> None:
    theirs = make_exchange(make_organization()).messages.get(role="assistant")

    assert agent_client.post(f"/api/v1/messages/{theirs.id}/feedback/", {"rating": 1}).status_code == 404


def test_tickets_list_filter_and_update(
    agent_client: APIClient, organization: Organization, agent: Membership, owner: Membership
) -> None:
    conversation = make_exchange(organization)
    mine = HandoffTicket.objects.create(
        organization=organization,
        conversation=conversation,
        requester_email="jo@example.net",
        assigned_to=agent.user,
    )
    HandoffTicket.objects.create(
        organization=organization,
        conversation=conversation,
        requester_email="sam@example.net",
        status="resolved",
    )

    listed = agent_client.get("/api/v1/tickets/").json()
    assert listed["count"] == 2
    assert listed["results"][0]["conversation_title"] == conversation.title
    assert agent_client.get("/api/v1/tickets/?assigned_to=me").json()["count"] == 1
    assert agent_client.get("/api/v1/tickets/?assigned_to=none").json()["count"] == 1
    assert agent_client.get(f"/api/v1/tickets/?assigned_to={agent.user_id}").json()["count"] == 1
    assert agent_client.get("/api/v1/tickets/?status=resolved").json()["count"] == 1
    assert agent_client.get("/api/v1/tickets/?search=SAM").json()["count"] == 1
    assert agent_client.get("/api/v1/tickets/?assigned_to=someone").status_code == 400

    url = f"/api/v1/tickets/{mine.id}/"
    resolved = agent_client.patch(
        url, {"status": "resolved", "assigned_to": str(owner.user_id), "note": "Done."}
    )
    assert resolved.status_code == 200
    body = resolved.json()
    assert body["status"] == "resolved"
    assert body["resolved_at"] is not None
    assert body["assigned_to"]["id"] == str(owner.user_id)

    reopened = agent_client.patch(url, {"status": "open", "assigned_to": None}, format="json").json()
    assert reopened["resolved_at"] is None
    assert reopened["assigned_to"] is None


def test_tickets_can_only_be_assigned_to_members(
    agent_client: APIClient, organization: Organization, make_user: Callable[..., User]
) -> None:
    ticket = HandoffTicket.objects.create(
        organization=organization, conversation=make_exchange(organization), requester_email="jo@example.net"
    )

    response = agent_client.patch(f"/api/v1/tickets/{ticket.id}/", {"assigned_to": str(make_user().id)})

    assert response.status_code == 400
    assert "assigned_to" in response.json()["error"]["details"]


def test_tickets_are_isolated(
    agent_client: APIClient, make_organization: Callable[..., Organization]
) -> None:
    other = make_organization()
    theirs = HandoffTicket.objects.create(
        organization=other, conversation=make_exchange(other), requester_email="jo@example.net"
    )

    assert agent_client.get("/api/v1/tickets/").json()["count"] == 0
    assert agent_client.get(f"/api/v1/tickets/{theirs.id}/").status_code == 404


def test_provider_status_panel(
    agent_client: APIClient, settings: Any, knowledge_base: dict[str, Document]
) -> None:
    settings.LLM_PROVIDER = "auto"
    settings.ANTHROPIC_API_KEY = "sk-ant-test-secret"

    response = agent_client.get("/api/v1/assistant/providers/")

    assert response.status_code == 200
    body = response.json()
    assert body["configured"] == "auto"
    assert body["active"] == {"name": "extractive", "model": "extractive-v1"}
    providers = {p["name"]: p for p in body["providers"]}
    assert providers["ollama"]["available"] is False
    assert providers["claude"]["available"] is True
    assert providers["claude"]["model"] == settings.CLAUDE_MODEL
    assert providers["extractive"]["available"] is True
    assert body["embedder"] == {
        "configured": "hashing",
        "active": "hashing-v1",
        "dimensions": 768,
        "stale_documents": 0,
    }
    assert "sk-ant-test-secret" not in response.content.decode()


def test_search_preview(agent_client: APIClient, knowledge_base: dict[str, Document]) -> None:
    response = agent_client.post(
        "/api/v1/assistant/search/", {"query": "how long do refunds take", "top_k": 3}
    )

    assert response.status_code == 200
    body = response.json()
    assert body["embedder"] == "hashing-v1"
    assert body["would_answer"] is True
    assert len(body["results"]) <= 3
    top = body["results"][0]
    assert top["document_id"] == str(knowledge_base["refunds"].id)
    assert set(top) == {
        "chunk_id", "document_id", "document_title", "location", "heading", "snippet", "score",
        "similarity", "vector_rank", "keyword_rank",
    }  # fmt: skip


@pytest.mark.parametrize("payload", [{"query": ""}, {"query": "refunds", "top_k": 21}, {}])
def test_search_validates_input(agent_client: APIClient, payload: dict[str, Any]) -> None:
    response = agent_client.post("/api/v1/assistant/search/", payload, format="json")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_endpoints_need_a_member(
    api_client: APIClient, organization: Organization, make_member: Callable[..., Membership]
) -> None:
    outsider = APIClient()
    outsider.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(make_member().user)}",
        HTTP_X_ORGANIZATION_ID=str(organization.id),
    )

    assert api_client.get("/api/v1/conversations/").status_code == 401
    response = outsider.get("/api/v1/tickets/")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"
