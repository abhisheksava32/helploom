"""Conversations, messages with their answer metadata, citations and handoff tickets."""

from __future__ import annotations

from django.conf import settings
from django.db import models

from core.models import OrganizationQuerySet, TimeStampedModel, UUIDModel


class Channel(models.TextChoices):
    WIDGET = "widget", "Website widget"
    PLAYGROUND = "playground", "Dashboard playground"


class ConversationStatus(models.TextChoices):
    OPEN = "open", "Open"
    HANDED_OFF = "handed_off", "Handed off"
    CLOSED = "closed", "Closed"


class Conversation(TimeStampedModel):
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="conversations"
    )
    channel = models.CharField(max_length=12, choices=Channel.choices)
    status = models.CharField(
        max_length=12, choices=ConversationStatus.choices, default=ConversationStatus.OPEN
    )
    title = models.CharField(max_length=200, blank=True, help_text="First question, shortened.")
    # Random id the widget keeps in localStorage; lets a visitor resume a conversation.
    visitor_id = models.CharField(max_length=64, blank=True)
    started_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    origin = models.CharField(max_length=255, blank=True)
    page_url = models.URLField(max_length=1000, blank=True)
    ip_hash = models.CharField(max_length=64, blank=True)
    user_agent = models.CharField(max_length=300, blank=True)
    message_count = models.PositiveIntegerField(default=0)
    last_message_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["-last_message_at", "-created_at"]
        indexes = [
            models.Index(fields=["organization", "-last_message_at"], name="assistant_conv_org_recent"),
            models.Index(fields=["organization", "channel"], name="assistant_conv_org_channel"),
            models.Index(fields=["organization", "visitor_id"], name="assistant_conv_org_visitor"),
        ]

    def __str__(self) -> str:
        return self.title or str(self.id)


class MessageRole(models.TextChoices):
    USER = "user", "User"
    ASSISTANT = "assistant", "Assistant"


class MessageStatus(models.TextChoices):
    STREAMING = "streaming", "Streaming"
    COMPLETE = "complete", "Complete"
    TRUNCATED = "truncated", "Truncated"
    FAILED = "failed", "Failed"


class AnswerType(models.TextChoices):
    ANSWERED = "answered", "Answered"
    NOT_FOUND = "not_found", "Not found in documentation"
    REFUSED = "refused", "Refused"
    ERROR = "error", "Error"


class Provider(models.TextChoices):
    OLLAMA = "ollama", "Ollama"
    CLAUDE = "claude", "Claude API"
    EXTRACTIVE = "extractive", "Extractive (offline)"


class Rating(models.IntegerChoices):
    DOWN = -1, "Thumbs down"
    UP = 1, "Thumbs up"


class Message(UUIDModel):
    """One turn. Assistant turns carry provider, timing, token usage and cost so the
    reports never need to recompute them."""

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="+")
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="messages")
    role = models.CharField(max_length=10, choices=MessageRole.choices)
    content = models.TextField(blank=True)
    # Lower cased, punctuation stripped copy of a user question, used to group top questions.
    normalized_content = models.CharField(max_length=300, blank=True)
    status = models.CharField(max_length=10, choices=MessageStatus.choices, default=MessageStatus.COMPLETE)
    answer_type = models.CharField(max_length=10, choices=AnswerType.choices, blank=True)
    reply_to = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="replies",
        help_text="For assistant messages: the user message being answered.",
    )
    provider = models.CharField(max_length=12, choices=Provider.choices, blank=True)
    model = models.CharField(max_length=100, blank=True, help_text="Model that actually served the answer.")
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    first_token_ms = models.PositiveIntegerField(null=True, blank=True)
    input_tokens = models.PositiveIntegerField(default=0)
    output_tokens = models.PositiveIntegerField(default=0)
    cache_read_input_tokens = models.PositiveIntegerField(default=0)
    cache_creation_input_tokens = models.PositiveIntegerField(default=0)
    cost_usd = models.DecimalField(max_digits=12, decimal_places=6, default=0)
    # Best vector similarity seen during retrieval; logged to tune RELEVANCE_THRESHOLD.
    top_score = models.FloatField(null=True, blank=True)
    rating = models.SmallIntegerField(choices=Rating.choices, null=True, blank=True)
    feedback_comment = models.TextField(blank=True)
    rated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        indexes = [
            models.Index(fields=["conversation", "created_at"], name="assistant_msg_conv_created"),
            models.Index(fields=["organization", "created_at"], name="assistant_msg_org_created"),
            models.Index(fields=["organization", "answer_type"], name="assistant_msg_org_answer"),
            models.Index(fields=["organization", "normalized_content"], name="assistant_msg_org_question"),
        ]

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:60]}"


class Citation(UUIDModel):
    """A [n] marker in an answer resolved to the passage it points at. Title, location and
    snippet are copied so history stays readable after a document is deleted."""

    message = models.ForeignKey(Message, on_delete=models.CASCADE, related_name="citations")
    marker = models.PositiveSmallIntegerField(help_text="The n in [n].")
    document = models.ForeignKey(
        "knowledge.Document", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    chunk = models.ForeignKey(
        "knowledge.Chunk", on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    document_title = models.CharField(max_length=255)
    location = models.CharField(max_length=120, blank=True)
    snippet = models.TextField()
    score = models.FloatField(null=True, blank=True)

    class Meta:
        ordering = ["marker"]
        constraints = [
            models.UniqueConstraint(fields=["message", "marker"], name="assistant_citation_unique_marker"),
        ]

    def __str__(self) -> str:
        return f"[{self.marker}] {self.document_title}"


class TicketStatus(models.TextChoices):
    OPEN = "open", "Open"
    PENDING = "pending", "Pending"
    RESOLVED = "resolved", "Resolved"


class HandoffTicket(TimeStampedModel):
    """Created when a visitor asks for a human, usually after a "not found" answer."""

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="tickets"
    )
    conversation = models.ForeignKey(Conversation, on_delete=models.CASCADE, related_name="tickets")
    status = models.CharField(max_length=10, choices=TicketStatus.choices, default=TicketStatus.OPEN)
    requester_email = models.EmailField()
    requester_name = models.CharField(max_length=150, blank=True)
    note = models.TextField(blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    resolved_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="assistant_ticket_org_status"),
        ]

    def __str__(self) -> str:
        return f"Ticket {self.requester_email} ({self.status})"
