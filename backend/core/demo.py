"""Demo workspace for a fresh clone: `uv run python manage.py seed_demo`.

Builds a populated dashboard from the same code paths the product uses: the sample
knowledge base in evals/kb/ goes through the real ingestion pipeline, and every
example conversation is answered by assistant.services.stream_answer with whichever
embedder and provider are active. Afterwards the timestamps are spread over the last
two weeks so the reports have a shape. Nothing here is a fixture that could drift
from the real behaviour.

It lives in core because it composes the public services of every app; the imports
sit inside the functions so core never depends on the apps at import time.
"""

from __future__ import annotations

import logging
import secrets
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Literal

from asgiref.sync import async_to_sync
from django.conf import settings
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)

DEMO_EMAIL = "demo@helploom.dev"
DEMO_NAME = "Avery Lindqvist"
DEMO_ORGANIZATION = "Kettlewick Coffee Co."
DEMO_PLAN = "starter"
SITE_ORIGIN = "https://www.kettlewick.example"

TEAMMATES = (
    ("priya.shah@kettlewick.example", "Priya Shah", "admin"),
    ("marco.ruiz@kettlewick.example", "Marco Ruiz", "agent"),
)
PENDING_INVITE = ("sam.okafor@kettlewick.example", "agent")

COLLECTIONS: dict[str, tuple[str, tuple[str, ...]]] = {
    "Orders and delivery": (
        "Shipping, returns and refunds.",
        ("shipping-and-delivery.md", "returns-and-refunds.html"),
    ),
    "Accounts and billing": (
        "Subscriptions, payments and account security.",
        ("subscriptions-and-billing.md", "account-and-security.txt"),
    ),
    "Products and rewards": (
        "Equipment care, warranty and the rewards program.",
        ("equipment-care-and-warranty.docx", "rewards-program.pdf"),
    ),
}
TAGS: dict[str, tuple[str, ...]] = {
    "shipping-and-delivery.md": ("shipping", "orders"),
    "returns-and-refunds.html": ("returns", "policy"),
    "subscriptions-and-billing.md": ("billing", "subscriptions"),
    "account-and-security.txt": ("account", "security"),
    "equipment-care-and-warranty.docx": ("equipment", "warranty"),
    "rewards-program.pdf": ("rewards",),
}


@dataclass(frozen=True)
class Handoff:
    email: str
    name: str
    note: str
    resolved: bool = False


@dataclass(frozen=True)
class Script:
    """One example conversation: who asked, when, what, and how it ended."""

    channel: Literal["widget", "playground"]
    days_ago: int
    hour: int
    questions: tuple[str, ...]
    rating: int | None = None
    comment: str = ""
    handoff: Handoff | None = None


CONVERSATIONS: tuple[Script, ...] = (
    Script(
        "widget", 13, 9, ("How long does standard shipping take?", "And when is shipping free?"), rating=1
    ),
    Script("widget", 12, 14, ("Can I send back a bag of coffee I already opened?",), rating=1),
    Script(
        "widget",
        11,
        11,
        ("Do you have a cafe I can visit in Portland?",),
        handoff=Handoff("noor.haddad@example.com", "Noor Haddad", "Asked about visiting in person.", True),
    ),
    Script("widget", 10, 16, ("My Mill M2 shows error E2, what does it mean?",), rating=1),
    Script("playground", 9, 10, ("How do I descale the kettle?",)),
    Script(
        "widget",
        8,
        13,
        ("How long is the warranty on the Pourwell kettle?", "What do I need to make a warranty claim?"),
        rating=1,
    ),
    Script("widget", 7, 15, ("Do you accept PayPal or Apple Pay?",), rating=1),
    Script(
        "widget",
        6,
        10,
        ("Do you offer wholesale pricing for my cafe?",),
        handoff=Handoff("lena.vogel@example.com", "Lena Vogel", "Runs a cafe, wants a wholesale quote."),
    ),
    Script("widget", 5, 12, ("How many reward points do I earn per dollar?", "Do my rewards points expire?")),
    Script(
        "widget",
        4,
        17,
        ("How long until I get my refund?",),
        rating=-1,
        comment="I wanted to know the exact day it lands.",
    ),
    Script("widget", 3, 9, ("How do I set up two-step verification?",), rating=1),
    Script("widget", 2, 18, ("Do you have a student discount?",)),
    Script("widget", 2, 11, ("What is the deadline to skip next week's subscription delivery?",), rating=1),
    Script("playground", 1, 14, ("What perks do Roast tier members get?",)),
    Script("widget", 1, 10, ("Are you hiring baristas?",)),
    Script("widget", 0, 8, ("Can I use two promo codes on one order?",)),
    # Busier days, so the daily charts look like real traffic rather than a flat line.
    Script("widget", 9, 15, ("Which carriers do you use?",), rating=1),
    Script("widget", 9, 19, ("How long is the password reset link valid?",)),
    Script("widget", 7, 9, ("How often should I clean the burrs of my grinder?",), rating=1),
    Script("widget", 7, 12, ("Is it ok to clean the grinder with rice?",)),
    Script("widget", 7, 20, ("What will the weather be like in Chicago tomorrow?",)),
    Script("widget", 5, 8, ("What happens when my card payment fails?",), rating=1),
    Script("widget", 5, 16, ("How long can I pause my subscription?",)),
    Script("widget", 3, 13, ("What do I get for referring a friend?",), rating=1),
    Script("widget", 3, 16, ("How much are 100 points worth?",)),
    Script("widget", 3, 19, ("Are your bags compostable?",)),
    Script("widget", 1, 16, ("Can I get a copy of my personal data?",)),
    Script("widget", 1, 18, ("How much is international shipping to Australia?",), rating=1),
    Script("widget", 0, 9, ("Do you accept PayPal or Apple Pay?",)),
)


@dataclass
class DemoSummary:
    email: str
    password: str
    organization_id: str
    site_key: str
    documents: int = 0
    conversations: int = 0
    tickets: int = 0
    answer_types: dict[str, int] = field(default_factory=dict)


class DemoExists(Exception):
    """The demo workspace is already there and reset was not asked for."""


def demo_exists() -> bool:
    from accounts.models import User

    return User.objects.filter(email=DEMO_EMAIL).exists()


def remove_demo() -> None:
    """Delete the demo user, their workspaces, the teammates and the stored files."""
    from accounts.models import Membership, Organization, User
    from knowledge.models import Document
    from knowledge.services import delete_document

    user = User.objects.filter(email=DEMO_EMAIL).first()
    if user is not None:
        organization_ids = list(
            Membership.objects.filter(user=user, role="owner").values_list("organization_id", flat=True)
        )
        for document in Document.objects.filter(organization_id__in=organization_ids):
            delete_document(document)
        Organization.objects.filter(pk__in=organization_ids).delete()
        user.delete()
    User.objects.filter(email__in=[email for email, _, _ in TEAMMATES]).delete()


def seed_demo(
    *, password: str | None = None, reset: bool = False, log: Callable[[str], None] = logger.info
) -> DemoSummary:
    from accounts import services as accounts_services
    from accounts.models import Invitation, Membership, Role, User
    from billing.services import apply_plan, get_subscription
    from widget.services import get_widget, update_widget

    if demo_exists():
        if not reset:
            raise DemoExists(f"{DEMO_EMAIL} already exists. Run with --reset to rebuild the demo workspace.")
        log("Removing the previous demo workspace")
        remove_demo()

    password = password or f"demo-{secrets.token_urlsafe(9)}"
    problems = accounts_services.password_errors(password, email=DEMO_EMAIL, full_name=DEMO_NAME)
    if problems:
        raise ValueError(" ".join(problems))

    with transaction.atomic():
        owner = accounts_services.signup(
            email=DEMO_EMAIL, password=password, organization_name=DEMO_ORGANIZATION, full_name=DEMO_NAME
        )
        organization = owner.organization
        organization.assistant_tone = "friendly"
        organization.save(update_fields=["assistant_tone", "updated_at"])
        # Starter has room for the team below; demo billing switches plans instantly.
        apply_plan(get_subscription(organization.pk), DEMO_PLAN)
        widget = update_widget(
            get_widget(organization),
            title="Kettlewick help",
            greeting="Hi there! Ask me anything about orders, brewing gear or your account.",
            brand_color="#b45309",
            allowed_origins=[SITE_ORIGIN],
        )
        members = {}
        for email, name, role in TEAMMATES:
            user = User.objects.create_user(email=email, password=secrets.token_urlsafe(24), full_name=name)
            members[role] = Membership.objects.create(user=user, organization=organization, role=role)
        # Created directly rather than through accounts.services.invite so seeding does
        # not print an invitation email; the token is random and never shown.
        Invitation.objects.create(
            organization=organization,
            email=PENDING_INVITE[0],
            role=PENDING_INVITE[1],
            invited_by=owner.user,
            token_hash=Invitation.new_token()[1],
            expires_at=timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS),
        )
    log(f"Created {DEMO_EMAIL} and the {DEMO_ORGANIZATION} workspace")

    summary = DemoSummary(
        email=DEMO_EMAIL,
        password=password,
        organization_id=str(organization.pk),
        site_key=widget.site_key,
    )
    summary.documents = _load_documents(organization, owner.user)
    log(f"Indexed {summary.documents} sample documents")

    agent = members[Role.AGENT].user
    for script in CONVERSATIONS:
        answer_types = _play(script, organization.pk, owner.user.pk, agent.pk)
        summary.conversations += 1
        summary.tickets += int(script.handoff is not None)
        for answer_type in answer_types:
            summary.answer_types[answer_type] = summary.answer_types.get(answer_type, 0) + 1
    log(f"Recorded {summary.conversations} example conversations and {summary.tickets} handoff tickets")
    return summary


def _load_documents(organization: Any, uploaded_by: Any) -> int:
    from evals.runner import kb_files
    from knowledge.models import DocumentStatus
    from knowledge.services import create_collection, create_document, ingest_document

    collection_for: dict[str, Any] = {}
    for name, (description, filenames) in COLLECTIONS.items():
        collection = create_collection(organization, name=name, description=description)
        for filename in filenames:
            collection_for[filename] = collection

    count = 0
    for path in kb_files():
        document = create_document(
            organization,
            filename=path.name,
            data=path.read_bytes(),
            uploaded_by=uploaded_by,
            collection=collection_for.get(path.name),
            tags=TAGS.get(path.name, ()),
        )
        # Inline rather than queued: the command should finish with everything ready.
        ingest_document(document.pk)
        document.refresh_from_db()
        if document.status != DocumentStatus.READY:
            raise RuntimeError(f"{path.name} did not index: {document.error_message}")
        count += 1
    return count


async def _collect(stream: Any) -> list[dict[str, Any]]:
    return [frame async for frame in stream]


def _ask(request: Any) -> dict[str, Any]:
    from assistant.services import stream_answer

    frames = async_to_sync(_collect)(stream_answer(request))
    done = next((frame for frame in frames if frame["type"] == "message.done"), None)
    if done is None:
        error = next((frame for frame in frames if frame["type"] == "error"), {})
        raise RuntimeError(f"The demo question failed: {error.get('message', 'no answer')}")
    return done


def _play(script: Script, organization_id: uuid.UUID, owner_id: uuid.UUID, agent_id: uuid.UUID) -> list[str]:
    from assistant import services as assistant_services
    from assistant.models import Conversation, HandoffTicket, Message
    from assistant.services import AskRequest, VisitorContext, apply_feedback

    visitor = None
    if script.channel == "widget":
        visitor = VisitorContext(
            visitor_id=f"v_{uuid.uuid4().hex[:20]}",
            origin=SITE_ORIGIN,
            page_url=f"{SITE_ORIGIN}/help",
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 Safari/605.1.15",
        )
    conversation_id: uuid.UUID | None = None
    answer_types: list[str] = []
    last_answer_id = ""
    for question in script.questions:
        done = _ask(
            AskRequest(
                organization_id=organization_id,
                channel=script.channel,
                content=question,
                conversation_id=conversation_id,
                user_id=owner_id if visitor is None else None,
                visitor=visitor,
            )
        )
        conversation_id = uuid.UUID(done["conversation_id"])
        last_answer_id = done["message_id"]
        answer_types.append(done["answer_type"])

    assert conversation_id is not None
    if script.rating is not None:
        apply_feedback(Message.objects.get(pk=last_answer_id), script.rating, script.comment)
    if script.handoff is not None:
        async_to_sync(assistant_services.create_handoff_ticket)(
            organization_id=organization_id,
            conversation_id=conversation_id,
            email=script.handoff.email,
            name=script.handoff.name,
            note=script.handoff.note,
            visitor_id=visitor.visitor_id if visitor else None,
        )
        if script.handoff.resolved:
            ticket = HandoffTicket.objects.get(conversation_id=conversation_id)
            assistant_services.update_ticket(ticket, status="resolved", assigned_to=agent_id)

    _backdate(Conversation.objects.get(pk=conversation_id), script)
    return answer_types


def _backdate(conversation: Any, script: Script) -> None:
    """Move a conversation and everything in it to the scripted day and hour."""
    from assistant.models import HandoffTicket, Message

    now = timezone.now()
    start = (now - timedelta(days=script.days_ago)).replace(hour=script.hour, minute=7, second=0)
    if start > now:
        start = now - timedelta(minutes=30)
    shift = start - conversation.created_at
    messages = list(Message.objects.filter(conversation=conversation).order_by("created_at"))
    for message in messages:
        Message.objects.filter(pk=message.pk).update(created_at=message.created_at + shift)
        if message.rated_at is not None:
            Message.objects.filter(pk=message.pk).update(rated_at=message.rated_at + shift)
    last = messages[-1].created_at + shift if messages else start
    type(conversation).objects.filter(pk=conversation.pk).update(
        created_at=start, updated_at=last, last_message_at=last
    )
    for ticket in HandoffTicket.objects.filter(conversation=conversation):
        resolved = ticket.resolved_at + shift if ticket.resolved_at else None
        HandoffTicket.objects.filter(pk=ticket.pk).update(
            created_at=ticket.created_at + shift, updated_at=ticket.updated_at + shift, resolved_at=resolved
        )
