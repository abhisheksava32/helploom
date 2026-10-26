"""Serializers for conversations, messages, citations, feedback and tickets.

Owner: backend-ai. Field names follow docs/API.md, sections "Conversations" and
"Tickets". The websocket frames reuse the same names. Every output field is listed
explicitly so a new column cannot leak through the API.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import serializers

from knowledge.serializers import UserRefSerializer

from .models import (
    AnswerType,
    Channel,
    Citation,
    Conversation,
    ConversationStatus,
    HandoffTicket,
    Message,
    Provider,
    TicketStatus,
)


class CitationSerializer(serializers.ModelSerializer):
    document_id = serializers.UUIDField(allow_null=True, read_only=True)
    chunk_id = serializers.UUIDField(allow_null=True, read_only=True)

    class Meta:
        model = Citation
        fields = ["marker", "document_id", "chunk_id", "document_title", "location", "snippet", "score"]
        read_only_fields = fields


def usage_of(message: Message) -> dict[str, int]:
    return {
        "input_tokens": message.input_tokens,
        "output_tokens": message.output_tokens,
        "cache_read_input_tokens": message.cache_read_input_tokens,
        "cache_creation_input_tokens": message.cache_creation_input_tokens,
    }


class MessageSerializer(serializers.ModelSerializer):
    reply_to = serializers.UUIDField(source="reply_to_id", allow_null=True, read_only=True)
    usage = serializers.SerializerMethodField()
    cost_usd = serializers.DecimalField(
        max_digits=12, decimal_places=6, coerce_to_string=True, read_only=True
    )
    citations = CitationSerializer(many=True, read_only=True)

    class Meta:
        model = Message
        fields = [
            "id",
            "role",
            "content",
            "status",
            "answer_type",
            "reply_to",
            "provider",
            "model",
            "latency_ms",
            "first_token_ms",
            "usage",
            "cost_usd",
            "rating",
            "feedback_comment",
            "citations",
            "created_at",
        ]
        read_only_fields = fields

    def get_usage(self, message: Message) -> dict[str, int]:
        return usage_of(message)


class TicketSerializer(serializers.ModelSerializer):
    conversation_id = serializers.UUIDField(read_only=True)
    conversation_title = serializers.CharField(source="conversation.title", read_only=True)
    assigned_to = UserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = HandoffTicket
        fields = [
            "id",
            "conversation_id",
            "conversation_title",
            "status",
            "requester_email",
            "requester_name",
            "note",
            "assigned_to",
            "created_at",
            "updated_at",
            "resolved_at",
        ]
        read_only_fields = fields


class ConversationSummarySerializer(serializers.ModelSerializer):
    """Expects a queryset from assistant.services.annotate_summaries()."""

    started_by = UserRefSerializer(read_only=True, allow_null=True)
    last_answer_type = serializers.CharField(read_only=True, default="")
    providers = serializers.ListField(child=serializers.CharField(), read_only=True, default=list)
    thumbs_up = serializers.IntegerField(read_only=True, default=0)
    thumbs_down = serializers.IntegerField(read_only=True, default=0)
    open_tickets = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "channel",
            "status",
            "title",
            "message_count",
            "last_message_at",
            "created_at",
            "started_by",
            "visitor_id",
            "origin",
            "page_url",
            "last_answer_type",
            "providers",
            "thumbs_up",
            "thumbs_down",
            "open_tickets",
        ]
        read_only_fields = fields

    def to_representation(self, instance: Conversation) -> dict[str, Any]:
        data = super().to_representation(instance)
        data["last_answer_type"] = data.get("last_answer_type") or ""
        data["providers"] = sorted(data.get("providers") or [])
        return data


class ConversationDetailSerializer(ConversationSummarySerializer):
    messages = MessageSerializer(many=True, read_only=True)
    tickets = TicketSerializer(many=True, read_only=True)

    class Meta(ConversationSummarySerializer.Meta):
        fields = [*ConversationSummarySerializer.Meta.fields, "messages", "tickets"]
        read_only_fields = fields


class ConversationUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=ConversationStatus.choices)


class ConversationListQuerySerializer(serializers.Serializer):
    channel = serializers.ChoiceField(choices=Channel.choices, required=False)
    status = serializers.ChoiceField(choices=ConversationStatus.choices, required=False)
    answer_type = serializers.ChoiceField(choices=AnswerType.choices, required=False)
    rating = serializers.ChoiceField(choices=["up", "down"], required=False)
    provider = serializers.ChoiceField(choices=Provider.choices, required=False)
    has_ticket = serializers.BooleanField(required=False, allow_null=True, default=None)
    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    search = serializers.CharField(required=False, max_length=200)
    ordering = serializers.CharField(required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        start, end = attrs.get("date_from"), attrs.get("date_to")
        if start and end and start > end:
            raise serializers.ValidationError({"date_from": ["date_from must not be after date_to."]})
        return attrs


class FeedbackSerializer(serializers.Serializer):
    rating = serializers.ChoiceField(choices=[1, -1], allow_null=True)
    comment = serializers.CharField(required=False, allow_blank=True, max_length=1000, default="")


class TicketUpdateSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TicketStatus.choices, required=False)
    assigned_to = serializers.UUIDField(required=False, allow_null=True)
    note = serializers.CharField(required=False, allow_blank=True, max_length=2000)


class TicketListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=TicketStatus.choices, required=False)
    assigned_to = serializers.CharField(required=False)
    search = serializers.CharField(required=False, max_length=200)
    ordering = serializers.CharField(required=False)

    def validate_assigned_to(self, value: str) -> str:
        if value in ("me", "none"):
            return value
        try:
            return str(serializers.UUIDField().to_internal_value(value))
        except serializers.ValidationError as exc:
            raise serializers.ValidationError('Use a user id, "me" or "none".') from exc


class SearchRequestSerializer(serializers.Serializer):
    query = serializers.CharField(min_length=1, max_length=settings.ASSISTANT_MAX_QUESTION_CHARS)
    top_k = serializers.IntegerField(required=False, min_value=1, max_value=20)


class SearchResultSerializer(serializers.Serializer):
    chunk_id = serializers.UUIDField()
    document_id = serializers.UUIDField()
    document_title = serializers.CharField()
    location = serializers.CharField(allow_blank=True)
    heading = serializers.CharField(allow_blank=True)
    snippet = serializers.CharField(allow_blank=True)
    score = serializers.FloatField()
    similarity = serializers.FloatField(allow_null=True)
    vector_rank = serializers.IntegerField(allow_null=True)
    keyword_rank = serializers.IntegerField(allow_null=True)


class SearchResponseSerializer(serializers.Serializer):
    query = serializers.CharField()
    embedder = serializers.CharField()
    threshold = serializers.FloatField()
    top_similarity = serializers.FloatField(allow_null=True)
    keyword_hits = serializers.IntegerField()
    would_answer = serializers.BooleanField()
    results = SearchResultSerializer(many=True)
