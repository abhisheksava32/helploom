"""Conversations, messages and citations."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from django.db import IntegrityError

from accounts.models import Organization
from assistant.models import Channel, Citation, Conversation, Message, MessageRole


@pytest.mark.django_db
def test_a_citation_marker_is_unique_per_message(organization: Organization) -> None:
    conversation = Conversation.objects.create(organization=organization, channel=Channel.PLAYGROUND)
    message = Message.objects.create(
        organization=organization, conversation=conversation, role=MessageRole.ASSISTANT, content="See [1]."
    )
    Citation.objects.create(message=message, marker=1, document_title="Refund policy", snippet="30 days")

    with pytest.raises(IntegrityError):
        Citation.objects.create(message=message, marker=1, document_title="Other", snippet="x")


@pytest.mark.django_db
def test_messages_are_scoped_by_organization(
    organization: Organization, make_organization: Callable[..., Organization]
) -> None:
    other = make_organization()
    for org in (organization, other):
        conversation = Conversation.objects.create(organization=org, channel=Channel.WIDGET)
        Message.objects.create(
            organization=org, conversation=conversation, role=MessageRole.USER, content="Hi"
        )

    assert Message.objects.for_organization(organization).count() == 1
