"""Report query parameters and the paginated unanswered row. The other report bodies
are built by analytics.services as plain dicts with the docs/API.md field names."""

from __future__ import annotations

import datetime as dt
from typing import Any

from django.utils import timezone
from rest_framework import serializers

from .services import ReportRange

DEFAULT_DAYS = 30
MAX_SPAN_DAYS = 366


class ReportRangeSerializer(serializers.Serializer):
    """?date_from=&date_to= (inclusive, UTC; default the last 30 days) and ?channel=."""

    date_from = serializers.DateField(required=False)
    date_to = serializers.DateField(required=False)
    channel = serializers.ChoiceField(choices=["widget", "playground"], required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        today = timezone.now().astimezone(dt.UTC).date()
        date_to = attrs.get("date_to") or today
        date_from = attrs.get("date_from") or date_to - dt.timedelta(days=DEFAULT_DAYS - 1)
        if date_from > date_to:
            raise serializers.ValidationError({"date_from": ["date_from must be on or before date_to."]})
        if (date_to - date_from).days + 1 > MAX_SPAN_DAYS:
            raise serializers.ValidationError(
                {"date_from": [f"Choose a range of at most {MAX_SPAN_DAYS} days."]}
            )
        attrs["report"] = ReportRange(date_from=date_from, date_to=date_to, channel=attrs.get("channel"))
        return attrs


class TopListSerializer(ReportRangeSerializer):
    limit = serializers.IntegerField(min_value=1, max_value=50, default=10)


class UnansweredQuestionSerializer(serializers.Serializer):
    message_id = serializers.UUIDField(source="id", read_only=True)
    conversation_id = serializers.UUIDField(read_only=True)
    question = serializers.CharField(source="content", read_only=True)
    channel = serializers.CharField(read_only=True)
    asked_at = serializers.DateTimeField(source="created_at", read_only=True)
    top_similarity = serializers.FloatField(read_only=True, allow_null=True)
    has_ticket = serializers.BooleanField(read_only=True)
