"""seed_demo builds a complete workspace through the real pipeline and refuses to run
twice unless asked to reset."""

from __future__ import annotations

from io import StringIO

import pytest
from django.core.management import CommandError, call_command

from accounts.models import Invitation, Membership, User
from assistant.models import Conversation, HandoffTicket, Message
from billing.models import Subscription
from core import demo
from knowledge.models import Collection, Document, DocumentStatus

PASSWORD = "a long demo passphrase"


@pytest.mark.django_db(transaction=True)
def test_seed_demo_builds_a_populated_workspace() -> None:
    out = StringIO()

    call_command("seed_demo", "--password", PASSWORD, stdout=out)

    user = User.objects.get(email=demo.DEMO_EMAIL)
    assert user.check_password(PASSWORD)
    organization = Membership.objects.get(user=user).organization
    assert organization.name == demo.DEMO_ORGANIZATION
    assert Subscription.objects.get(organization=organization).plan == demo.DEMO_PLAN
    assert Membership.objects.filter(organization=organization).count() == 1 + len(demo.TEAMMATES)
    assert Invitation.objects.filter(organization=organization, accepted_at__isnull=True).count() == 1

    documents = Document.objects.filter(organization=organization)
    assert documents.count() == 6
    assert set(documents.values_list("status", flat=True)) == {DocumentStatus.READY}
    assert Collection.objects.filter(organization=organization).count() == len(demo.COLLECTIONS)

    conversations = Conversation.objects.filter(organization=organization)
    assert conversations.count() == len(demo.CONVERSATIONS)
    assert conversations.filter(channel="playground").exists()
    answers = Message.objects.filter(organization=organization, role="assistant")
    assert answers.filter(answer_type="answered").exists()
    assert answers.filter(answer_type="not_found").exists()
    assert answers.filter(rating=-1).exists()
    tickets = HandoffTicket.objects.filter(organization=organization)
    assert tickets.count() == 2
    assert tickets.filter(status="resolved", assigned_to__isnull=False).count() == 1

    # Spread over two weeks, so the reports have more than one day to show.
    days = {c.created_at.date() for c in conversations}
    assert len(days) >= 10
    assert PASSWORD in out.getvalue()


@pytest.mark.django_db(transaction=True)
def test_seed_demo_refuses_to_run_twice_unless_reset() -> None:
    call_command("seed_demo", "--password", PASSWORD, stdout=StringIO())

    with pytest.raises(CommandError, match="--reset"):
        call_command("seed_demo", stdout=StringIO())

    call_command("seed_demo", "--reset", "--password", PASSWORD, stdout=StringIO())
    assert User.objects.filter(email=demo.DEMO_EMAIL).count() == 1
    assert Document.objects.count() == 6


@pytest.mark.django_db
def test_seed_demo_rejects_a_weak_password() -> None:
    with pytest.raises(CommandError, match="Choose another password"):
        call_command("seed_demo", "--password", "12345", stdout=StringIO())
