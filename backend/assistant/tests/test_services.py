"""The answer pipeline (stream_answer) and the socket services around it.

The pipeline hops threads through database_sync_to_async, so these tests use
transactional databases: rows must be committed to be visible from the worker thread.
"""

from __future__ import annotations

import uuid
from collections.abc import Callable
from decimal import Decimal
from typing import Any

import pytest
from channels.db import database_sync_to_async
from rest_framework.exceptions import NotFound, ValidationError

from accounts.models import Membership, Organization
from assistant import services
from assistant.models import Citation, Conversation, HandoffTicket, Message
from assistant.prompts import NOT_FOUND_SENTENCE, refusal_answer
from assistant.providers import StopReason, Usage
from assistant.services import AskRequest, VisitorContext, compute_cost
from billing.models import UsageCounter
from billing.services import current_period_start
from knowledge.models import Document

from .conftest import ScriptedProvider

transactional = pytest.mark.django_db(transaction=True)
REFUND_QUESTION = "How long do refunds take?"


async def run_sync[T](func: Callable[[], T]) -> T:
    return await database_sync_to_async(func)()


def ask(organization: Organization, content: str = REFUND_QUESTION, **extra: Any) -> AskRequest:
    extra.setdefault("channel", "playground")
    return AskRequest(organization_id=organization.id, content=content, client_message_id="c-1", **extra)


async def collect(request: AskRequest) -> list[dict[str, Any]]:
    return [frame async for frame in services.stream_answer(request)]


def frame_types(frames: list[dict[str, Any]]) -> list[str]:
    return [frame["type"] for frame in frames]


@transactional
async def test_an_answer_streams_frames_in_protocol_order(
    owner: Membership, knowledge_base: dict[str, Document], org_events: list[dict[str, Any]]
) -> None:
    organization = owner.organization
    frames = await collect(ask(organization, user_id=owner.user_id))

    types = frame_types(frames)
    assert types[0] == "message.start"
    assert types[-2:] == ["message.citations", "message.done"]
    assert set(types[1:-2]) == {"message.delta"}

    start, citations, done = frames[0], frames[-2], frames[-1]
    assert start["client_message_id"] == "c-1"
    assert {start["message_id"], citations["message_id"], done["message_id"]} == {start["message_id"]}
    assert "".join(f["delta"] for f in frames[1:-2]) == done["content"]
    assert done["answer_type"] == "answered"
    assert done["status"] == "complete"
    assert done["provider"] == "extractive"
    assert done["model"] == "extractive-v1"
    assert done["offer_handoff"] is False
    assert done["cost_usd"] == "0.000000"
    assert done["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }
    assert "5 business days" in done["content"]
    assert citations["citations"][0]["document_id"] == str(knowledge_base["refunds"].id)
    assert citations["citations"][0]["marker"] == 1

    def stored() -> tuple[Conversation, list[Message], int]:
        conversation = Conversation.objects.get(pk=start["conversation_id"])
        messages = list(conversation.messages.order_by("created_at"))
        return conversation, messages, Citation.objects.filter(message=messages[1]).count()

    conversation, messages, citation_count = await run_sync(stored)
    assert conversation.channel == "playground"
    assert conversation.started_by_id == owner.user_id
    assert conversation.title == REFUND_QUESTION
    assert conversation.message_count == 2
    user_message, answer = messages
    assert (user_message.role, user_message.normalized_content) == ("user", "how long do refunds take")
    assert answer.reply_to_id == user_message.id
    assert answer.content == done["content"]
    assert answer.latency_ms is not None and answer.first_token_ms is not None
    assert answer.top_score is not None and answer.top_score > 0
    assert citation_count == len(citations["citations"])
    assert [e["type"] for e in org_events] == ["conversation.created"]
    assert org_events[0]["conversation"]["last_answer_type"] == "answered"


@transactional
async def test_follow_ups_continue_the_conversation_with_history(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any, org_events: list[Any]
) -> None:
    provider = use_provider(ScriptedProvider(["Refunds take 5 business days [1]."]))
    first = await collect(ask(organization))
    conversation_id = uuid.UUID(first[0]["conversation_id"])

    second = await collect(ask(organization, "And what about exchanges?", conversation_id=conversation_id))

    assert second[0]["conversation_id"] == str(conversation_id)
    history = [(m.role, m.content) for m in provider.prompts[1].messages[:-1]]
    assert history == [("user", REFUND_QUESTION), ("assistant", "Refunds take 5 business days.")]
    count = await run_sync(lambda: Conversation.objects.get(pk=conversation_id).message_count)
    assert count == 4
    assert [e["type"] for e in org_events] == ["conversation.created", "conversation.updated"]


@transactional
async def test_irrelevant_questions_get_not_found_without_calling_a_model(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    provider = use_provider(ScriptedProvider())

    frames = await collect(ask(organization, "Who won the football world cup in 2014?"))

    done = frames[-1]
    assert provider.prompts == []
    assert done["answer_type"] == "not_found"
    assert done["content"].startswith(NOT_FOUND_SENTENCE)
    assert done["offer_handoff"] is True
    assert done["model"] == services.RELEVANCE_GATE_MODEL
    assert frames[-2]["citations"] == []


@transactional
async def test_a_model_saying_not_found_is_recorded_as_not_found(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider([NOT_FOUND_SENTENCE]))

    done = (await collect(ask(organization)))[-1]

    assert done["answer_type"] == "not_found"
    assert done["offer_handoff"] is True


@transactional
async def test_markers_without_a_passage_are_dropped(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider(["Refunds take 5 days [1][7]."]))

    frames = await collect(ask(organization))

    assert frames[-1]["content"] == "Refunds take 5 days [1]."
    assert [c["marker"] for c in frames[-2]["citations"]] == [1]


@transactional
async def test_the_plan_limit_is_a_single_error_frame(organization: Organization) -> None:
    await run_sync(
        lambda: UsageCounter.objects.create(
            organization=organization, period_start=current_period_start(), messages=200
        )
    )

    frames = await collect(ask(organization))

    assert frame_types(frames) == ["error"]
    error = frames[0]
    assert error["code"] == "plan_limit_exceeded"
    assert error["client_message_id"] == "c-1"
    assert error["details"] == {"limit": "messages", "used": 200, "allowed": 200, "plan": "free"}
    assert not await run_sync(lambda: Message.objects.exists())


@transactional
@pytest.mark.parametrize("content", ["", "   ", "x" * 2001])
async def test_invalid_questions_are_validation_errors(organization: Organization, content: str) -> None:
    frames = await collect(ask(organization, content))

    assert frame_types(frames) == ["error"]
    assert frames[0]["code"] == "validation_error"
    assert "content" in frames[0]["details"]


@transactional
async def test_unknown_conversations_are_not_found(organization: Organization) -> None:
    frames = await collect(ask(organization, conversation_id=uuid.uuid4()))

    assert frame_types(frames) == ["error"]
    assert frames[0]["code"] == "not_found"
    # Nothing was counted against the plan.
    assert not await run_sync(lambda: UsageCounter.objects.filter(messages__gt=0).exists())


@transactional
async def test_widget_visitors_cannot_continue_each_others_conversations(
    organization: Organization, knowledge_base: dict[str, Document]
) -> None:
    alice = VisitorContext(
        visitor_id="v_alice_000000000001",
        origin="https://shop.example.com",
        page_url="javascript:alert(1)",
        ip_hash="abc",
        user_agent="Firefox",
    )
    first = await collect(ask(organization, channel="widget", visitor=alice))
    conversation_id = uuid.UUID(first[0]["conversation_id"])

    conversation = await run_sync(lambda: Conversation.objects.get(pk=conversation_id))
    assert (conversation.visitor_id, conversation.origin, conversation.ip_hash) == (
        "v_alice_000000000001",
        "https://shop.example.com",
        "abc",
    )
    assert conversation.page_url == ""  # never store a script URL as a link

    bob = VisitorContext(visitor_id="v_bob_00000000000002")
    frames = await collect(ask(organization, channel="widget", visitor=bob, conversation_id=conversation_id))
    assert frames[0]["code"] == "not_found"

    # A playground socket cannot hijack a widget conversation either.
    frames = await collect(ask(organization, conversation_id=conversation_id))
    assert frames[0]["code"] == "not_found"


@transactional
async def test_provider_failures_fall_back_to_extractive(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider(["Partial claude text"], fail_after=1))

    frames = await collect(ask(organization))

    done = frames[-1]
    assert done["provider"] == "extractive"
    assert done["answer_type"] == "answered"
    assert "Partial claude text" not in done["content"]
    assert "5 business days" in done["content"]


@transactional
async def test_refusals_answer_politely_and_offer_a_human(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider(["I will not"], stop_reason=StopReason.REFUSAL, model="claude-opus-4-8"))

    frames = await collect(ask(organization))

    done = frames[-1]
    assert done["answer_type"] == "refused"
    assert done["content"] == refusal_answer("friendly")
    assert done["model"] == "claude-opus-4-8"
    assert done["offer_handoff"] is True
    assert frames[-2]["citations"] == []


@transactional
async def test_max_tokens_marks_the_answer_truncated(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider(["Refunds take [1]"], stop_reason=StopReason.MAX_TOKENS))

    done = (await collect(ask(organization)))[-1]

    assert done["status"] == "truncated"
    assert done["answer_type"] == "answered"


@transactional
async def test_cancel_stops_the_stream_and_saves_a_truncated_answer(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider([f"word{i} " for i in range(50)], delay=0.01))
    frames: list[dict[str, Any]] = []

    async for frame in services.stream_answer(ask(organization)):
        frames.append(frame)
        if frame["type"] == "message.delta" and len(frames) == 2:
            assert services.cancel_answer(frame["message_id"]) is True

    done = frames[-1]
    assert done["type"] == "message.done"
    assert done["status"] == "truncated"
    assert done["content"] == "word0"
    assert services.cancel_answer(done["message_id"]) is False  # no longer streaming
    status = await run_sync(lambda: Message.objects.get(pk=done["message_id"]).status)
    assert status == "truncated"


@transactional
async def test_a_consumer_that_goes_away_leaves_a_truncated_answer(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider(["Refunds take ", "5 days [1].", " More."], delay=0.01))
    stream = services.stream_answer(ask(organization))
    start = await anext(stream)
    first_delta = await anext(stream)

    await stream.aclose()  # what happens when the socket's task stops iterating

    assert first_delta["delta"] == "Refunds take "
    message = await run_sync(lambda: Message.objects.get(pk=start["message_id"]))
    assert (message.status, message.content) == ("truncated", "Refunds take")


@transactional
async def test_claude_usage_and_cost_are_recorded(
    organization: Organization, knowledge_base: dict[str, Document], use_provider: Any, settings: Any
) -> None:
    settings.LLM_PRICING_PER_MTOK = {
        "claude-opus-5-5": {"input": "4.00", "output": "20.00", "cache_read": "0.20", "cache_write": "5.00"}
    }
    usage = Usage(
        input_tokens=1000, output_tokens=500, cache_read_input_tokens=2000, cache_creation_input_tokens=0
    )
    use_provider(ScriptedProvider(["Refunds take 5 days [1]."], usage=usage))

    done = (await collect(ask(organization)))[-1]

    assert done["provider"] == "claude"
    assert done["cost_usd"] == "0.014400"
    assert done["usage"]["cache_read_input_tokens"] == 2000
    message = await run_sync(lambda: Message.objects.get(pk=done["message_id"]))
    assert (message.input_tokens, message.output_tokens, message.cost_usd) == (1000, 500, Decimal("0.014400"))


def test_compute_cost_is_zero_for_unpriced_models() -> None:
    assert compute_cost("llama3.2", Usage(input_tokens=10**6)) == Decimal("0")


# Handoff, feedback and history


def _widget_conversation(
    organization: Organization, visitor_id: str = "v_alice_000000000001"
) -> Conversation:
    conversation = Conversation.objects.create(
        organization=organization, channel="widget", visitor_id=visitor_id, title="Refunds?"
    )
    user = Message.objects.create(
        organization=organization, conversation=conversation, role="user", content="Refunds?"
    )
    answer = Message.objects.create(
        organization=organization,
        conversation=conversation,
        role="assistant",
        content="Within 30 days [1].",
        answer_type="answered",
        provider="extractive",
        reply_to=user,
    )
    Citation.objects.create(message=answer, marker=1, document_title="Refund policy", snippet="30 days")
    return conversation


@transactional
async def test_handoff_creates_a_ticket_and_hands_the_conversation_off(
    organization: Organization, org_events: list[dict[str, Any]]
) -> None:
    conversation = await run_sync(lambda: _widget_conversation(organization))

    frame = await services.create_handoff_ticket(
        organization_id=organization.id,
        conversation_id=conversation.id,
        email="Jo@Example.net",
        name="Jo",
        note="Please call me.",
        visitor_id="v_alice_000000000001",
    )

    assert frame["type"] == "handoff.created"
    assert frame["ticket"]["conversation_id"] == str(conversation.id)
    assert frame["ticket"]["status"] == "open"
    ticket = await run_sync(lambda: HandoffTicket.objects.get(pk=frame["ticket"]["id"]))
    assert (ticket.requester_email, ticket.requester_name) == ("jo@example.net", "Jo")
    status = await run_sync(lambda: Conversation.objects.get(pk=conversation.id).status)
    assert status == "handed_off"
    assert [e["type"] for e in org_events] == ["ticket.created", "conversation.updated"]
    assert org_events[0]["ticket"]["conversation_title"] == "Refunds?"
    assert org_events[1]["conversation"]["open_tickets"] == 1


@transactional
async def test_handoff_validates_and_checks_the_visitor(organization: Organization) -> None:
    conversation = await run_sync(lambda: _widget_conversation(organization))

    with pytest.raises(ValidationError):
        await services.create_handoff_ticket(
            organization_id=organization.id, conversation_id=conversation.id, email="not-an-email"
        )
    with pytest.raises(NotFound):
        await services.create_handoff_ticket(
            organization_id=organization.id,
            conversation_id=conversation.id,
            email="jo@example.net",
            visitor_id="v_mallory_0000000003",
        )


@transactional
async def test_feedback_rates_answers_for_their_own_visitor_only(
    organization: Organization, org_events: list[Any]
) -> None:
    conversation = await run_sync(lambda: _widget_conversation(organization))
    user_id, answer_id = await run_sync(
        lambda: tuple(conversation.messages.order_by("created_at").values_list("id", flat=True))
    )

    frame = await services.record_feedback(
        organization_id=organization.id, message_id=answer_id, rating=1, visitor_id="v_alice_000000000001"
    )
    assert frame == {"type": "feedback.ok", "message_id": str(answer_id), "rating": 1}

    cleared = await services.record_feedback(
        organization_id=organization.id, message_id=answer_id, rating=None
    )
    assert cleared["rating"] is None

    with pytest.raises(ValidationError):
        await services.record_feedback(organization_id=organization.id, message_id=user_id, rating=1)
    with pytest.raises(NotFound):
        await services.record_feedback(
            organization_id=organization.id,
            message_id=answer_id,
            rating=-1,
            visitor_id="v_mallory_0000000003",
        )


@transactional
async def test_history_is_scoped_to_the_visitor_and_organization(
    organization: Organization, make_organization: Callable[..., Organization]
) -> None:
    conversation = await run_sync(lambda: _widget_conversation(organization))
    other = await run_sync(make_organization)

    frame = await services.conversation_history(
        organization_id=organization.id, conversation_id=conversation.id, visitor_id="v_alice_000000000001"
    )

    assert frame is not None
    assert frame["type"] == "conversation.history"
    assert [m["role"] for m in frame["messages"]] == ["user", "assistant"]
    assert frame["messages"][1]["citations"][0]["document_title"] == "Refund policy"
    assert (
        await services.conversation_history(
            organization_id=organization.id,
            conversation_id=conversation.id,
            visitor_id="v_mallory_0000000003",
        )
        is None
    )
    assert (
        await services.conversation_history(organization_id=other.id, conversation_id=conversation.id) is None
    )
