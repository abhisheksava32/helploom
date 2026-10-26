"""A small, fully known support history for the report tests.

Organisation A, 1 to 3 October 2026 (UTC):

    conv_refunds   widget      1 Oct  "How long do refunds take?"  answered (ollama, +1)
                               2 Oct  "how long do refunds take"   answered (claude, -1, $0.004120)
    conv_iceland   playground  2 Oct  "Do you ship to Iceland?"    not_found (0.12), ticket
    conv_order     widget      3 Oct  "Where is my order?"         error (extractive)

plus one question on 30 September (outside the range) and organisation B's own
conversation on 2 October, which must never show up.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

import pytest

from accounts.models import Organization
from assistant.models import Citation, Conversation, HandoffTicket, Message
from knowledge.models import Document


def at(day: int, hour: int = 12, month: int = 10) -> dt.datetime:
    return dt.datetime(2026, month, day, hour, tzinfo=dt.UTC)


@dataclass
class Seed:
    organization: Organization
    other: Organization
    refund_doc: Document
    shipping_doc: Document
    iceland_question: Message


def make_document(organization: Organization, title: str) -> Document:
    return Document.objects.create(
        organization=organization,
        title=title,
        original_filename=f"{title}.md",
        file=f"documents/{organization.id}/{title}.md",
        content_type="text/markdown",
        file_size=100,
        checksum=title.ljust(64, "0")[:64],
        status="ready",
    )


def conversation(organization: Organization, channel: str, created: dt.datetime) -> Conversation:
    conv = Conversation.objects.create(organization=organization, channel=channel, title="q")
    Conversation.objects.filter(pk=conv.pk).update(created_at=created)
    return conv


def ask(conv: Conversation, text: str, when: dt.datetime, **answer: Any) -> tuple[Message, Message]:
    question = Message.objects.create(
        organization_id=conv.organization_id,
        conversation=conv,
        role="user",
        content=text,
        normalized_content=text.lower().strip(" ?"),
    )
    reply = Message.objects.create(
        organization_id=conv.organization_id, conversation=conv, role="assistant", reply_to=question, **answer
    )
    Message.objects.filter(pk=question.pk).update(created_at=when)
    Message.objects.filter(pk=reply.pk).update(created_at=when + dt.timedelta(seconds=2))
    return question, reply


def cite(message: Message, marker: int, document: Document) -> Citation:
    return Citation.objects.create(
        message=message,
        marker=marker,
        document=document,
        document_title=document.title,
        snippet="...",
        score=0.7,
    )


@pytest.fixture
def seed(make_organization: Callable[..., Organization]) -> Seed:
    org = make_organization(name="Northwind")
    other = make_organization(name="Other")
    refund_doc = make_document(org, "Refund policy")
    shipping_doc = make_document(org, "Shipping guide")
    old_doc = make_document(org, "Old policy")

    refunds = conversation(org, "widget", at(1, 9))
    _, first = ask(
        refunds,
        "How long do refunds take?",
        at(1, 10),
        answer_type="answered",
        provider="ollama",
        model="llama3.2",
        latency_ms=1000,
        first_token_ms=200,
        rating=1,
    )
    cite(first, 1, refund_doc)
    cite(first, 2, shipping_doc)
    cite(first, 3, old_doc)
    old_doc.delete()  # citations keep the copied title

    _, second = ask(
        refunds,
        "how long do refunds take",
        at(2, 10),
        answer_type="answered",
        provider="claude",
        model="claude-opus-5-5",
        latency_ms=3000,
        first_token_ms=400,
        rating=-1,
        input_tokens=1000,
        output_tokens=100,
        cache_read_input_tokens=500,
        cost_usd=Decimal("0.004120"),
    )
    cite(second, 1, refund_doc)

    iceland = conversation(org, "playground", at(2, 8))
    iceland_question, _ = ask(
        iceland, "Do you ship to Iceland?", at(2, 11), answer_type="not_found", top_score=0.12
    )
    ticket = HandoffTicket.objects.create(
        organization=org, conversation=iceland, requester_email="jo@example.net"
    )
    HandoffTicket.objects.filter(pk=ticket.pk).update(created_at=at(2, 12))

    order = conversation(org, "widget", at(3, 8))
    ask(
        order,
        "Where is my order?",
        at(3, 9),
        answer_type="error",
        provider="extractive",
        model="extractive-v1",
    )

    ask(refunds, "Old question", at(30, month=9), answer_type="answered", provider="ollama", model="llama3.2")

    elsewhere = conversation(other, "widget", at(2))
    ask(
        elsewhere,
        "How long do refunds take?",
        at(2, 10),
        answer_type="not_found",
        provider="claude",
        model="claude-opus-5-5",
        cost_usd=Decimal("9"),
    )

    return Seed(org, other, refund_doc, shipping_doc, iceland_question)
