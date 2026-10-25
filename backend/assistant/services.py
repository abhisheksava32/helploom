"""Answer pipeline and conversation services. Owner: backend-ai.

Both chat sockets (assistant.consumers.ChatConsumer for the dashboard playground and
widget.consumers.WidgetConsumer for the public widget) call only the functions below,
so their signatures are a contract between the two backend owners. See
docs/DESIGN.md, "Service interfaces between apps", and the frame shapes in
docs/API.md, "Chat protocol".

The scaffold pins the signatures; the implementation replaces the bodies.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal
from uuid import UUID

# One server frame as sent on the wire, for example
# {"type": "message.delta", "message_id": "...", "delta": "Our refund window"}.
ServerFrame = dict[str, Any]

Channel = Literal["widget", "playground"]


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


def stream_answer(request: AskRequest) -> AsyncIterator[ServerFrame]:
    """Answer one question and yield its frames in protocol order.

    message.start, message.delta (zero or more), message.citations, message.done; or a
    single error frame. Handles plan limits (billing.services.consume_message_quota),
    retrieval, the relevance threshold, provider selection and fallback, persistence
    of both messages and their citations, and publishes conversation.created or
    conversation.updated with core.realtime. Never raises for expected failures: it
    yields an error frame instead, so consumers only forward what they receive.
    """
    raise NotImplementedError("The answer pipeline is implemented by backend-ai.")


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
    raise NotImplementedError("Handoff is implemented by backend-ai.")


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
    raise NotImplementedError("Feedback is implemented by backend-ai.")


async def conversation_history(
    *,
    organization_id: UUID,
    conversation_id: UUID,
    visitor_id: str | None = None,
) -> ServerFrame | None:
    """Return the conversation.history frame, or None when the conversation does not
    exist, belongs to another organisation, or (widget) to another visitor."""
    raise NotImplementedError("History is implemented by backend-ai.")
