"""Answer pipeline and conversation services. Owner: backend-ai.

Both chat sockets (assistant.consumers.ChatConsumer for the dashboard playground and
widget.consumers.WidgetConsumer for the public widget) call only the async functions
in the first half of this module, so their signatures are a contract between the two
backend owners (docs/DESIGN.md, "Ownership and service interfaces"). The frames they
yield are the wire format in docs/API.md, "Chat frames"; consumers forward them
unchanged.

One question flows like this:

    validate -> quota (billing) -> conversation + user message + placeholder answer
    -> message.start -> hybrid retrieval -> relevance gate
       below threshold: the fixed "not found" answer, no model call
       otherwise: prompt -> provider stream (fallback to extractive on failure)
    -> citations parsed from the final text -> answer saved with usage and cost
    -> message.citations, message.done -> conversation.created/updated on ws/dashboard/

The second half holds the synchronous services behind the REST views.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncGenerator, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal
from uuid import UUID

from channels.db import database_sync_to_async
from django.conf import settings
from django.contrib.postgres.expressions import ArraySubquery
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import Count, Exists, F, IntegerField, OuterRef, Prefetch, Q, QuerySet, Subquery, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from rest_framework.exceptions import APIException, NotFound, ValidationError

from billing.services import consume_message_quota
from core.exceptions import PlanLimitExceeded
from core.realtime import abroadcast_org_event, broadcast_org_event

from .citations import CitationRef, parse_citations
from .models import (
    AnswerType,
    Citation,
    Conversation,
    ConversationStatus,
    HandoffTicket,
    Message,
    MessageRole,
    MessageStatus,
    Provider,
    TicketStatus,
)
from .prompts import (
    PromptMessage,
    build_prompt,
    history_messages,
    is_not_found,
    not_found_answer,
    refusal_answer,
)
from .providers import (
    Completed,
    ExtractiveProvider,
    ProviderError,
    StopReason,
    TextDelta,
    Usage,
    resolve_provider,
)
from .retrieval import RetrievalResult, search
from .text import conversation_title, normalize_question

if TYPE_CHECKING:
    from accounts.models import Organization, User

logger = logging.getLogger(__name__)

# One server frame as sent on the wire, for example
# {"type": "message.delta", "message_id": "...", "delta": "Our refund window"}.
ServerFrame = dict[str, Any]

Channel = Literal["widget", "playground"]

# Recorded as the model of answers the relevance gate produced without calling one.
RELEVANCE_GATE_MODEL = "relevance-gate"
HANDOFF_ANSWER_TYPES = {AnswerType.NOT_FOUND, AnswerType.REFUSED, AnswerType.ERROR}


@dataclass(frozen=True)
class VisitorContext:
    """Who is asking through the public widget. Built by the widget consumer."""

    visitor_id: str
    origin: str = ""
    page_url: str = ""
    ip_hash: str = ""
    user_agent: str = ""


@dataclass(frozen=True)
class AskRequest:
    """One question. Exactly one of user_id (playground) or visitor (widget) is set."""

    organization_id: UUID
    channel: Channel
    content: str
    client_message_id: str | None = None
    conversation_id: UUID | None = None
    user_id: UUID | None = None
    visitor: VisitorContext | None = None


def error_frame(
    code: str,
    message: str,
    *,
    details: dict[str, Any] | None = None,
    client_message_id: str | None = None,
    message_id: str | None = None,
) -> ServerFrame:
    frame: ServerFrame = {"type": "error", "code": code, "message": message, "details": details or {}}
    if client_message_id is not None:
        frame["client_message_id"] = client_message_id
    if message_id is not None:
        frame["message_id"] = message_id
    return frame


def first_error_message(detail: Any) -> str:
    if isinstance(detail, dict) and detail:
        return first_error_message(next(iter(detail.values())))
    if isinstance(detail, list) and detail:
        return first_error_message(detail[0])
    return str(detail)


# Cancellation. chat.cancel arrives on the socket while the answer streams in the same
# process, so an in-process registry of events is all that is needed.

_cancel_events: dict[str, asyncio.Event] = {}


def cancel_answer(message_id: UUID | str) -> bool:
    """Ask a streaming answer to stop. It then finishes with message.done and status
    "truncated". Returns False when no such answer is streaming in this process."""
    event = _cancel_events.get(str(message_id))
    if event is None:
        return False
    event.set()
    return True


# Starting a turn


@dataclass
class _Turn:
    organization_id: UUID
    business_name: str
    tone: str
    conversation: Conversation
    created_conversation: bool
    user_message: Message
    answer: Message
    history: list[PromptMessage]


def _validate_question(content: Any) -> str:
    question = content.strip() if isinstance(content, str) else ""
    if not question:
        raise ValidationError({"content": ["Type a question first."]})
    limit = settings.ASSISTANT_MAX_QUESTION_CHARS
    if len(question) > limit:
        raise ValidationError({"content": [f"Questions can be at most {limit} characters."]})
    return question


def _safe_url(value: str, limit: int) -> str:
    # Only web URLs are kept: the dashboard renders page_url as a link, and a
    # javascript: URL from a hostile page must never become one.
    value = value.strip()
    return value[:limit] if value.lower().startswith(("http://", "https://")) else ""


def find_conversation(
    organization_id: UUID | str, conversation_id: UUID | str, *, visitor_id: str | None = None
) -> Conversation | None:
    """A conversation of this organisation; on the widget also of this visitor, so one
    visitor can never read or continue another visitor's conversation."""
    queryset = Conversation.objects.for_organization(organization_id).filter(pk=conversation_id)
    if visitor_id is not None:
        queryset = queryset.filter(channel="widget", visitor_id=visitor_id)
    return queryset.first()


def _history(conversation: Conversation) -> list[PromptMessage]:
    turns = settings.ASSISTANT_HISTORY_TURNS
    if turns <= 0:
        return []
    rows = list(
        Message.objects.filter(conversation=conversation)
        .exclude(status__in=[MessageStatus.STREAMING, MessageStatus.FAILED])
        .order_by("-created_at")
        .values_list("role", "content")[:turns]
    )
    return history_messages(list(reversed(rows)), turns)


def _begin_turn(request: AskRequest, question: str) -> _Turn:
    from accounts.models import Organization

    organization = Organization.objects.filter(pk=request.organization_id).first()
    if organization is None:
        raise NotFound("This workspace does not exist.")
    visitor = request.visitor
    conversation: Conversation | None = None
    if request.conversation_id is not None:
        conversation = find_conversation(
            organization.pk, request.conversation_id, visitor_id=visitor.visitor_id if visitor else None
        )
        if conversation is None or conversation.channel != request.channel:
            raise NotFound("This conversation does not exist.")

    # Counted when the question is accepted, before any retrieval or model work.
    consume_message_quota(organization.pk)

    with transaction.atomic():
        created = conversation is None
        if conversation is None:
            conversation = Conversation.objects.create(
                organization=organization,
                channel=request.channel,
                title=conversation_title(question),
                started_by_id=request.user_id if request.channel == "playground" else None,
                visitor_id=visitor.visitor_id[:64] if visitor else "",
                origin=visitor.origin[:255] if visitor else "",
                page_url=_safe_url(visitor.page_url, 1000) if visitor else "",
                ip_hash=visitor.ip_hash[:64] if visitor else "",
                user_agent=visitor.user_agent[:300] if visitor else "",
            )
            history: list[PromptMessage] = []
        else:
            history = _history(conversation)
        user_message = Message.objects.create(
            organization=organization,
            conversation=conversation,
            role=MessageRole.USER,
            content=question,
            normalized_content=normalize_question(question),
            status=MessageStatus.COMPLETE,
        )
        answer = Message.objects.create(
            organization=organization,
            conversation=conversation,
            role=MessageRole.ASSISTANT,
            status=MessageStatus.STREAMING,
            reply_to=user_message,
        )
        now = timezone.now()
        Conversation.objects.filter(pk=conversation.pk).update(
            message_count=F("message_count") + 2, last_message_at=now, updated_at=now
        )
    return _Turn(
        organization_id=organization.pk,
        business_name=organization.name,
        tone=organization.assistant_tone,
        conversation=conversation,
        created_conversation=created,
        user_message=user_message,
        answer=answer,
        history=history,
    )


# Generating the answer


@dataclass
class AnswerOutcome:
    """Everything the pipeline learned while answering; persisted at the end."""

    parts: list[str] = field(default_factory=list)
    final_text: str | None = None
    provider: str = Provider.EXTRACTIVE
    model: str = ""
    stop_reason: str = StopReason.END_TURN
    usage: Usage = field(default_factory=Usage)
    first_token_ms: int | None = None
    cancelled: bool = False
    gated: bool = False
    retrieval: RetrievalResult | None = None
    # Filled in by resolve_outcome().
    content: str = ""
    answer_type: str = AnswerType.ANSWERED
    status: str = MessageStatus.COMPLETE
    citations: list[CitationRef] = field(default_factory=list)


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


async def generate_answer(
    *,
    organization_id: UUID | str,
    business_name: str,
    tone: str,
    question: str,
    history: Sequence[PromptMessage] = (),
    outcome: AnswerOutcome,
    started: float,
    cancel_event: asyncio.Event | None = None,
    retrieval: RetrievalResult | None = None,
) -> AsyncGenerator[str]:
    """Retrieve, gate and stream an answer as text deltas, filling `outcome`.

    Shared by the chat pipeline and the eval harness, so the evals measure exactly
    what customers get (the harness passes `retrieval` in, having run it in its own
    transaction). Provider failures are not errors: the extractive provider answers
    instead and outcome.provider says who did.
    """
    if retrieval is None:
        retrieval = await database_sync_to_async(search)(organization_id, question)
    outcome.retrieval = retrieval

    if not retrieval.would_answer:
        # Nothing relevant enough: answer honestly without calling any model, which
        # costs nothing and cannot hallucinate a policy.
        text = not_found_answer(tone)
        outcome.gated = True
        outcome.provider, outcome.model = Provider.EXTRACTIVE, RELEVANCE_GATE_MODEL
        outcome.final_text = text
        outcome.first_token_ms = _elapsed_ms(started)
        outcome.parts.append(text)
        yield text
        return

    prompt = build_prompt(
        business_name=business_name,
        tone=tone,
        question=question,
        passages=retrieval.passages,
        history=history,
    )
    provider = await resolve_provider()
    attempts = [provider] if isinstance(provider, ExtractiveProvider) else [provider, ExtractiveProvider()]
    for attempt in attempts:
        outcome.provider, outcome.model = attempt.name, attempt.model
        events = attempt.stream(prompt)
        try:
            async for event in events:
                if isinstance(event, TextDelta):
                    if not event.text:
                        continue
                    if outcome.first_token_ms is None:
                        outcome.first_token_ms = _elapsed_ms(started)
                    outcome.parts.append(event.text)
                    yield event.text
                    if cancel_event is not None and cancel_event.is_set():
                        outcome.cancelled = True
                        outcome.stop_reason = StopReason.CANCELLED
                        return
                elif isinstance(event, Completed):
                    outcome.model = event.model
                    outcome.stop_reason = event.stop_reason
                    outcome.usage = event.usage
                    outcome.final_text = event.text
            return
        except ProviderError as exc:
            logger.warning(
                "%s could not answer (%s); answering with the extractive provider", attempt.name, exc
            )
        except Exception:
            logger.exception("%s failed unexpectedly; answering with the extractive provider", attempt.name)
        finally:
            await events.aclose()
        # Whatever streamed before the failure is replaced by the fallback answer;
        # message.done carries the final text and the UI swaps it in.
        outcome.final_text = None
        outcome.usage = Usage()
        outcome.stop_reason = StopReason.END_TURN
    raise RuntimeError("Every provider failed, including the extractive one.")


def compute_cost(model: str, usage: Usage) -> Decimal:
    prices = settings.LLM_PRICING_PER_MTOK.get(model)
    if not prices:
        return Decimal("0.000000")
    total = (
        Decimal(prices["input"]) * usage.input_tokens
        + Decimal(prices["output"]) * usage.output_tokens
        + Decimal(prices.get("cache_read", "0")) * usage.cache_read_input_tokens
        + Decimal(prices.get("cache_write", "0")) * usage.cache_creation_input_tokens
    )
    return (total / Decimal(1_000_000)).quantize(Decimal("0.000001"))


def resolve_outcome(outcome: AnswerOutcome, tone: str) -> AnswerOutcome:
    """Decide the stored text, answer type, status and citations from what streamed."""
    passages = outcome.retrieval.passages if outcome.retrieval else []
    text = outcome.final_text if outcome.final_text is not None else "".join(outcome.parts)

    if outcome.gated:
        outcome.content, outcome.answer_type = text, AnswerType.NOT_FOUND
    elif outcome.stop_reason == StopReason.REFUSAL:
        # A refusal's partial output is discarded, never shown as an answer.
        outcome.content, outcome.answer_type = refusal_answer(tone), AnswerType.REFUSED
    elif not outcome.cancelled and (not text.strip() or is_not_found(text)):
        outcome.content, outcome.answer_type = not_found_answer(tone), AnswerType.NOT_FOUND
    else:
        outcome.content, outcome.citations = parse_citations(text, passages)
        outcome.answer_type = AnswerType.ANSWERED
    truncated = outcome.cancelled or outcome.stop_reason == StopReason.MAX_TOKENS
    outcome.status = MessageStatus.TRUNCATED if truncated else MessageStatus.COMPLETE
    return outcome


def _finish_turn(turn: _Turn, outcome: AnswerOutcome, latency_ms: int) -> tuple[Message, ServerFrame]:
    cost = compute_cost(outcome.model, outcome.usage)
    usage = outcome.usage
    with transaction.atomic():
        answer = Message.objects.select_for_update().get(pk=turn.answer.pk)
        answer.content = outcome.content
        answer.status = outcome.status
        answer.answer_type = outcome.answer_type
        answer.provider = outcome.provider
        answer.model = outcome.model[:100]
        answer.latency_ms = latency_ms
        answer.first_token_ms = outcome.first_token_ms
        answer.input_tokens = usage.input_tokens
        answer.output_tokens = usage.output_tokens
        answer.cache_read_input_tokens = usage.cache_read_input_tokens
        answer.cache_creation_input_tokens = usage.cache_creation_input_tokens
        answer.cost_usd = cost
        answer.top_score = outcome.retrieval.top_similarity if outcome.retrieval else None
        answer.save()
        # Idempotent: a save interrupted by a cancelled socket may be retried.
        Citation.objects.filter(message=answer).delete()
        Citation.objects.bulk_create(
            [
                Citation(
                    message=answer,
                    marker=ref.marker,
                    document_id=ref.passage.document_id,
                    chunk_id=ref.passage.chunk_id,
                    document_title=ref.passage.document_title[:255],
                    location=ref.passage.location[:120],
                    snippet=ref.snippet,
                    score=ref.passage.similarity,
                )
                for ref in outcome.citations
            ]
        )
        now = timezone.now()
        Conversation.objects.filter(pk=turn.conversation.pk).update(last_message_at=now, updated_at=now)
    event_type = "conversation.created" if turn.created_conversation else "conversation.updated"
    return answer, conversation_event(event_type, turn.conversation.pk)


def _fail_turn(turn: _Turn, latency_ms: int, outcome: AnswerOutcome) -> ServerFrame:
    Message.objects.filter(pk=turn.answer.pk).update(
        status=MessageStatus.FAILED,
        answer_type=AnswerType.ERROR,
        content="".join(outcome.parts),
        provider=outcome.provider,
        model=outcome.model[:100],
        latency_ms=latency_ms,
        first_token_ms=outcome.first_token_ms,
    )
    event_type = "conversation.created" if turn.created_conversation else "conversation.updated"
    return conversation_event(event_type, turn.conversation.pk)


def _done_frame(turn: _Turn, answer: Message, outcome: AnswerOutcome) -> ServerFrame:
    return {
        "type": "message.done",
        "message_id": str(answer.pk),
        "conversation_id": str(turn.conversation.pk),
        "status": answer.status,
        "answer_type": answer.answer_type,
        "content": answer.content,
        "provider": answer.provider,
        "model": answer.model,
        "latency_ms": answer.latency_ms,
        "first_token_ms": answer.first_token_ms,
        "usage": outcome.usage.as_dict(),
        "cost_usd": f"{answer.cost_usd:.6f}",
        "offer_handoff": answer.answer_type in HANDOFF_ANSWER_TYPES,
    }


async def stream_answer(request: AskRequest) -> AsyncGenerator[ServerFrame]:
    """Answer one question and yield its frames in protocol order.

    message.start, message.delta (zero or more), message.citations, message.done; or a
    single error frame. Handles plan limits (billing.services.consume_message_quota),
    retrieval, the relevance threshold, provider selection and fallback, persistence
    of both messages and their citations, and publishes conversation.created or
    conversation.updated with core.realtime. Never raises for expected failures: it
    yields an error frame instead, so consumers only forward what they receive.
    """
    client_message_id = request.client_message_id
    try:
        question = _validate_question(request.content)
        turn = await database_sync_to_async(_begin_turn)(request, question)
    except PlanLimitExceeded as exc:
        yield error_frame(
            "plan_limit_exceeded", str(exc.detail), details=exc.details, client_message_id=client_message_id
        )
        return
    except ValidationError as exc:
        details = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
        yield error_frame(
            "validation_error",
            first_error_message(exc.detail),
            details=details,
            client_message_id=client_message_id,
        )
        return
    except APIException as exc:
        code = exc.get_codes() if isinstance(exc.get_codes(), str) else exc.default_code
        yield error_frame(str(code), first_error_message(exc.detail), client_message_id=client_message_id)
        return
    except Exception:
        logger.exception("Could not start an answer for organization %s", request.organization_id)
        yield error_frame(
            "server_error",
            "Something went wrong on our side. Please try again.",
            client_message_id=client_message_id,
        )
        return

    message_id = str(turn.answer.pk)
    started = time.monotonic()
    cancel_event = asyncio.Event()
    _cancel_events[message_id] = cancel_event
    outcome = AnswerOutcome()
    try:
        yield {
            "type": "message.start",
            "client_message_id": client_message_id,
            "conversation_id": str(turn.conversation.pk),
            "user_message_id": str(turn.user_message.pk),
            "message_id": message_id,
            "created_at": turn.answer.created_at.isoformat().replace("+00:00", "Z"),
        }
        try:
            async for delta in generate_answer(
                organization_id=turn.organization_id,
                business_name=turn.business_name,
                tone=turn.tone,
                question=question,
                history=turn.history,
                outcome=outcome,
                started=started,
                cancel_event=cancel_event,
            ):
                yield {"type": "message.delta", "message_id": message_id, "delta": delta}
            resolve_outcome(outcome, turn.tone)
            answer, event = await database_sync_to_async(_finish_turn)(turn, outcome, _elapsed_ms(started))
        except (asyncio.CancelledError, GeneratorExit):
            # The consumer went away mid answer (socket closed, task cancelled). The
            # customer saw part of it, so store that part as a truncated answer rather
            # than leave the row "streaming" forever.
            outcome.cancelled = True
            resolve_outcome(outcome, turn.tone)
            await database_sync_to_async(_finish_turn)(turn, outcome, _elapsed_ms(started))
            raise
        except Exception:
            logger.exception("Answer %s failed", message_id)
            event = await database_sync_to_async(_fail_turn)(turn, _elapsed_ms(started), outcome)
            yield error_frame(
                "answer_failed",
                "Something went wrong while answering. Please try again.",
                client_message_id=client_message_id,
                message_id=message_id,
            )
            await abroadcast_org_event(turn.organization_id, event)
            return

        yield {
            "type": "message.citations",
            "message_id": message_id,
            "citations": [ref.as_frame() for ref in outcome.citations],
        }
        yield _done_frame(turn, answer, outcome)
        await abroadcast_org_event(turn.organization_id, event)
    finally:
        _cancel_events.pop(message_id, None)


# Handoff, feedback and history (sockets)


def _ticket_event(event_type: str, ticket: HandoffTicket) -> ServerFrame:
    from .serializers import TicketSerializer

    return {"type": event_type, "ticket": TicketSerializer(ticket).data}


def _create_ticket(
    organization_id: UUID | str,
    conversation_id: UUID | str,
    email: str,
    name: str,
    note: str,
    visitor_id: str | None,
) -> tuple[HandoffTicket, list[ServerFrame]]:
    email = (email or "").strip().lower()
    errors: dict[str, list[str]] = {}
    try:
        validate_email(email)
    except DjangoValidationError:
        errors["email"] = ["Enter a valid email address."]
    if len(name or "") > 150:
        errors["name"] = ["Use at most 150 characters."]
    if len(note or "") > 2000:
        errors["note"] = ["Use at most 2000 characters."]
    if errors:
        raise ValidationError(errors)
    conversation = find_conversation(organization_id, conversation_id, visitor_id=visitor_id)
    if conversation is None:
        raise NotFound("This conversation does not exist.")
    with transaction.atomic():
        ticket = HandoffTicket.objects.create(
            organization_id=conversation.organization_id,
            conversation=conversation,
            requester_email=email,
            requester_name=(name or "").strip(),
            note=(note or "").strip(),
        )
        Conversation.objects.filter(pk=conversation.pk).update(
            status=ConversationStatus.HANDED_OFF, updated_at=timezone.now()
        )
    ticket.conversation = conversation
    return ticket, [
        _ticket_event("ticket.created", ticket),
        conversation_event("conversation.updated", conversation.pk),
    ]


async def create_handoff_ticket(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    email: str,
    name: str = "",
    note: str = "",
    visitor_id: str | None = None,
) -> ServerFrame:
    """Create a HandoffTicket, mark the conversation handed_off, publish ticket.created
    and return the handoff.created frame. When visitor_id is given the conversation
    must belong to that visitor. Raises rest_framework ValidationError or NotFound."""
    ticket, events = await database_sync_to_async(_create_ticket)(
        organization_id, conversation_id, email, name, note, visitor_id
    )
    for event in events:
        await abroadcast_org_event(organization_id, event)
    return {
        "type": "handoff.created",
        "ticket": {
            "id": str(ticket.pk),
            "conversation_id": str(ticket.conversation_id),
            "status": ticket.status,
            "created_at": ticket.created_at.isoformat().replace("+00:00", "Z"),
        },
    }


def apply_feedback(message: Message, rating: int | None, comment: str = "") -> Message:
    if message.role != MessageRole.ASSISTANT:
        raise ValidationError({"rating": ["Only answers can be rated."]})
    if rating not in (1, -1, None):
        raise ValidationError({"rating": ["Use 1, -1 or null."]})
    comment = (comment or "").strip()
    if len(comment) > 1000:
        raise ValidationError({"comment": ["Use at most 1000 characters."]})
    message.rating = rating
    message.feedback_comment = comment if rating is not None else ""
    message.rated_at = timezone.now() if rating is not None else None
    message.save(update_fields=["rating", "feedback_comment", "rated_at"])
    return message


def _record_feedback(
    organization_id: UUID | str,
    message_id: UUID | str,
    rating: int | None,
    comment: str,
    visitor_id: str | None,
) -> tuple[Message, ServerFrame]:
    queryset = (
        Message.objects.for_organization(organization_id).select_related("conversation").filter(pk=message_id)
    )
    if visitor_id is not None:
        queryset = queryset.filter(conversation__channel="widget", conversation__visitor_id=visitor_id)
    message = queryset.first()
    if message is None:
        raise NotFound("This answer does not exist.")
    apply_feedback(message, rating, comment)
    return message, conversation_event("conversation.updated", message.conversation_id)


async def record_feedback(
    *,
    organization_id: UUID,
    message_id: UUID,
    rating: int | None,
    comment: str = "",
    visitor_id: str | None = None,
) -> ServerFrame:
    """Store a thumbs up (1), thumbs down (-1) or cleared (None) rating on an assistant
    message and return the feedback.ok frame. Same visitor rule as above."""
    message, event = await database_sync_to_async(_record_feedback)(
        organization_id, message_id, rating, comment, visitor_id
    )
    await abroadcast_org_event(organization_id, event)
    return {"type": "feedback.ok", "message_id": str(message.pk), "rating": message.rating}


def _history_frame(
    organization_id: UUID | str, conversation_id: UUID | str, visitor_id: str | None
) -> ServerFrame | None:
    from .serializers import CitationSerializer

    conversation = find_conversation(organization_id, conversation_id, visitor_id=visitor_id)
    if conversation is None:
        return None
    messages = (
        Message.objects.filter(conversation=conversation)
        .exclude(status__in=[MessageStatus.STREAMING, MessageStatus.FAILED])
        .prefetch_related("citations")
        .order_by("created_at")
    )
    return {
        "type": "conversation.history",
        "conversation_id": str(conversation.pk),
        "status": conversation.status,
        "messages": [
            {
                "id": str(message.pk),
                "role": message.role,
                "content": message.content,
                "answer_type": message.answer_type,
                "rating": message.rating,
                "citations": CitationSerializer(message.citations.all(), many=True).data,
                "created_at": message.created_at.isoformat().replace("+00:00", "Z"),
            }
            for message in messages
        ],
    }


async def conversation_history(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    visitor_id: str | None = None,
) -> ServerFrame | None:
    """Return the conversation.history frame, or None when the conversation does not
    exist, belongs to another organisation, or (widget) to another visitor."""
    return await database_sync_to_async(_history_frame)(organization_id, conversation_id, visitor_id)


# Conversations (REST)

CONVERSATION_ORDERING = {"last_message_at", "created_at", "message_count"}


def annotate_summaries(queryset: QuerySet[Conversation]) -> QuerySet[Conversation]:
    """Add the computed ConversationSummary fields with correlated subqueries, which
    stay cheap per page instead of joining every message of every conversation."""
    answers = Message.objects.filter(conversation=OuterRef("pk"), role=MessageRole.ASSISTANT)

    def rating_count(value: int) -> Coalesce:
        counts = (
            Message.objects.filter(conversation=OuterRef("pk"), rating=value)
            .order_by()
            .values("conversation")
            .annotate(n=Count("id"))
            .values("n")
        )
        return Coalesce(Subquery(counts, output_field=IntegerField()), Value(0))

    open_tickets = (
        HandoffTicket.objects.filter(
            conversation=OuterRef("pk"), status__in=[TicketStatus.OPEN, TicketStatus.PENDING]
        )
        .order_by()
        .values("conversation")
        .annotate(n=Count("id"))
        .values("n")
    )
    return queryset.select_related("started_by").annotate(
        last_answer_type=Subquery(
            answers.exclude(answer_type="").order_by("-created_at").values("answer_type")[:1]
        ),
        providers=ArraySubquery(
            answers.exclude(provider="").order_by("provider").values("provider").distinct()
        ),
        thumbs_up=rating_count(1),
        thumbs_down=rating_count(-1),
        open_tickets=Coalesce(Subquery(open_tickets, output_field=IntegerField()), Value(0)),
    )


def conversation_summary(conversation_id: UUID | str) -> Conversation:
    return annotate_summaries(Conversation.objects.filter(pk=conversation_id)).get()


def conversation_event(event_type: str, conversation_id: UUID | str) -> ServerFrame:
    from .serializers import ConversationSummarySerializer

    return {
        "type": event_type,
        "conversation": ConversationSummarySerializer(conversation_summary(conversation_id)).data,
    }


def _day_start(day: date) -> datetime:
    return datetime.combine(day, dt_time.min, tzinfo=UTC)


def conversation_queryset(
    organization: Organization,
    *,
    channel: str | None = None,
    status: str | None = None,
    answer_type: str | None = None,
    rating: str | None = None,
    provider: str | None = None,
    has_ticket: bool | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    search: str | None = None,
    ordering: str | None = None,
) -> QuerySet[Conversation]:
    queryset = Conversation.objects.for_organization(organization)
    messages = Message.objects.filter(conversation=OuterRef("pk"))
    if channel:
        queryset = queryset.filter(channel=channel)
    if status:
        queryset = queryset.filter(status=status)
    if answer_type:
        queryset = queryset.filter(
            Exists(messages.filter(role=MessageRole.ASSISTANT, answer_type=answer_type))
        )
    if rating:
        queryset = queryset.filter(Exists(messages.filter(rating=1 if rating == "up" else -1)))
    if provider:
        queryset = queryset.filter(Exists(messages.filter(role=MessageRole.ASSISTANT, provider=provider)))
    if has_ticket is not None:
        tickets = Exists(HandoffTicket.objects.filter(conversation=OuterRef("pk")))
        queryset = queryset.filter(tickets if has_ticket else ~tickets)
    if date_from:
        queryset = queryset.filter(created_at__gte=_day_start(date_from))
    if date_to:
        queryset = queryset.filter(created_at__lt=_day_start(date_to) + timedelta(days=1))
    if search:
        queryset = queryset.filter(
            Q(title__icontains=search) | Exists(messages.filter(content__icontains=search))
        )

    field_name = (ordering or "").lstrip("-")
    if field_name not in CONVERSATION_ORDERING:
        ordering, field_name = "-last_message_at", "last_message_at"
    expression = F(field_name)
    order = (
        expression.desc(nulls_last=True)
        if (ordering or "").startswith("-")
        else expression.asc(nulls_first=True)
    )
    return annotate_summaries(queryset).order_by(order, "-created_at", "id")


def conversation_detail_queryset(organization: Organization) -> QuerySet[Conversation]:
    return annotate_summaries(Conversation.objects.for_organization(organization)).prefetch_related(
        Prefetch("messages", queryset=Message.objects.order_by("created_at").prefetch_related("citations")),
        Prefetch(
            "tickets",
            queryset=HandoffTicket.objects.select_related("assigned_to", "conversation").order_by(
                "-created_at"
            ),
        ),
    )


def update_conversation(conversation: Conversation, *, status: str) -> Conversation:
    conversation.status = status
    conversation.save(update_fields=["status", "updated_at"])
    event = conversation_event("conversation.updated", conversation.pk)
    transaction.on_commit(lambda: broadcast_org_event(conversation.organization_id, event))
    return conversation_summary(conversation.pk)


def rate_message(message: Message, *, rating: int | None, comment: str = "") -> Message:
    apply_feedback(message, rating, comment)
    event = conversation_event("conversation.updated", message.conversation_id)
    transaction.on_commit(lambda: broadcast_org_event(message.organization_id, event))
    return Message.objects.prefetch_related("citations").get(pk=message.pk)


# Tickets (REST)

TICKET_ORDERING = {"created_at", "status"}


def ticket_queryset(
    organization: Organization,
    *,
    user: User | None = None,
    status: str | None = None,
    assigned_to: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
) -> QuerySet[HandoffTicket]:
    queryset = HandoffTicket.objects.for_organization(organization).select_related(
        "assigned_to", "conversation"
    )
    if status:
        queryset = queryset.filter(status=status)
    if assigned_to == "me":
        queryset = queryset.filter(assigned_to=user)
    elif assigned_to == "none":
        queryset = queryset.filter(assigned_to__isnull=True)
    elif assigned_to:
        queryset = queryset.filter(assigned_to_id=UUID(assigned_to))
    if search:
        queryset = queryset.filter(
            Q(requester_email__icontains=search)
            | Q(requester_name__icontains=search)
            | Q(note__icontains=search)
        )
    field_name = (ordering or "").lstrip("-")
    order = ordering if field_name in TICKET_ORDERING and ordering else "-created_at"
    return queryset.order_by(order, "id")


_UNSET: Any = object()


def update_ticket(
    ticket: HandoffTicket,
    *,
    status: str | None = None,
    assigned_to: UUID | None = _UNSET,
    note: str | None = None,
) -> HandoffTicket:
    from accounts.models import Membership

    fields: list[str] = []
    if assigned_to is not _UNSET:
        if assigned_to is None:
            ticket.assigned_to = None
        else:
            membership = (
                Membership.objects.for_organization(ticket.organization_id)
                .select_related("user")
                .filter(user_id=assigned_to)
                .first()
            )
            if membership is None:
                raise ValidationError({"assigned_to": ["Choose a member of this workspace."]})
            ticket.assigned_to = membership.user
        fields.append("assigned_to")
    if status is not None and status != ticket.status:
        ticket.status = status
        # resolved_at describes the current state: set on resolve, cleared on reopen.
        ticket.resolved_at = timezone.now() if status == TicketStatus.RESOLVED else None
        fields += ["status", "resolved_at"]
    if note is not None:
        ticket.note = note.strip()
        fields.append("note")
    if fields:
        ticket.save(update_fields=[*fields, "updated_at"])
        event = _ticket_event("ticket.updated", ticket)
        transaction.on_commit(lambda: broadcast_org_event(ticket.organization_id, event))
    return ticket


# Assistant status and retrieval preview (REST)


def provider_report(organization: Organization) -> dict[str, Any]:
    """The provider status panel: what is configured, what is reachable, what the next
    question will use. Never includes secrets."""
    from knowledge import ollama
    from knowledge.embeddings import DIMENSIONS, get_embedder
    from knowledge.services import stale_document_count

    from .providers import active_provider, claude_configured

    status = ollama.probe()
    model = settings.OLLAMA_MODEL
    if not status.reachable:
        ollama_detail = status.detail or f"Not reachable at {settings.OLLAMA_URL}."
    elif status.has_model(model):
        ollama_detail = f"Reachable at {settings.OLLAMA_URL}."
    else:
        ollama_detail = f"Reachable, but {model} is not pulled. Run: ollama pull {model}"
    claude_detail = (
        f"API key configured. Refused requests fall back to {settings.CLAUDE_FALLBACK_MODEL} on the server."
        if claude_configured()
        else "ANTHROPIC_API_KEY is not set."
    )
    active = active_provider()
    embedder = get_embedder()
    return {
        "configured": settings.LLM_PROVIDER,
        "active": {"name": active.name, "model": active.model},
        "providers": [
            {"name": "ollama", "available": status.has_model(model), "model": model, "detail": ollama_detail},
            {
                "name": "claude",
                "available": claude_configured(),
                "model": settings.CLAUDE_MODEL,
                "detail": claude_detail,
            },
            {
                "name": "extractive",
                "available": True,
                "model": ExtractiveProvider.model,
                "detail": "Offline answers built from the top passages.",
            },
        ],
        "embedder": {
            "configured": settings.EMBEDDER,
            "active": embedder.name,
            "dimensions": DIMENSIONS,
            "stale_documents": stale_document_count(organization, embedder.name),
        },
    }


def search_preview(organization: Organization, *, query: str, top_k: int | None = None) -> dict[str, Any]:
    """Retrieval only, for the playground's "show sources" view and threshold tuning."""
    from .citations import SNIPPET_MAX_CHARS
    from .text import shorten

    result = search(organization.pk, query.strip(), top_k=top_k)
    return {
        "query": result.query,
        "embedder": result.embedder,
        "threshold": result.threshold,
        "top_similarity": round(result.top_similarity, 4) if result.top_similarity is not None else None,
        "keyword_hits": result.keyword_hits,
        "would_answer": result.would_answer,
        "results": [
            {
                "chunk_id": passage.chunk_id,
                "document_id": passage.document_id,
                "document_title": passage.document_title,
                "location": passage.location,
                "heading": passage.heading,
                "snippet": shorten(passage.text, SNIPPET_MAX_CHARS),
                "score": round(passage.score, 6),
                "similarity": round(passage.similarity, 4) if passage.similarity is not None else None,
                "vector_rank": passage.vector_rank,
                "keyword_rank": passage.keyword_rank,
            }
            for passage in result.passages
        ],
    }
