"""Widget settings (dashboard), the public config response and the frames the public
socket accepts. Field names follow docs/API.md, sections "Widget" and "ws/widget/".
"""

from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from django.conf import settings
from rest_framework import serializers

from core.origins import normalize_origin

from . import services
from .models import WidgetConfig, WidgetPosition

MAX_ALLOWED_ORIGINS = 20


class WidgetSettingsSerializer(serializers.ModelSerializer):
    script_url = serializers.SerializerMethodField()
    ws_url = serializers.SerializerMethodField()
    embed_snippet = serializers.SerializerMethodField()

    class Meta:
        model = WidgetConfig
        fields = [
            "site_key",
            "is_enabled",
            "allowed_origins",
            "title",
            "greeting",
            "brand_color",
            "position",
            "script_url",
            "ws_url",
            "embed_snippet",
            "updated_at",
        ]
        read_only_fields = fields

    def get_script_url(self, widget: WidgetConfig) -> str:
        return services.script_url()

    def get_ws_url(self, widget: WidgetConfig) -> str:
        return services.ws_url()

    def get_embed_snippet(self, widget: WidgetConfig) -> str:
        return services.embed_snippet(widget)


class WidgetSettingsUpdateSerializer(serializers.Serializer):
    is_enabled = serializers.BooleanField(required=False)
    allowed_origins = serializers.ListField(child=serializers.CharField(max_length=255), required=False)
    title = serializers.CharField(min_length=1, max_length=60, required=False)
    greeting = serializers.CharField(min_length=1, max_length=300, required=False)
    brand_color = serializers.RegexField(
        r"^#[0-9a-fA-F]{6}$",
        required=False,
        error_messages={"invalid": "Use a hex colour like #4f46e5."},
    )
    position = serializers.ChoiceField(choices=WidgetPosition.choices, required=False)

    def validate_allowed_origins(self, values: list[str]) -> list[str]:
        cleaned: list[str] = []
        errors: list[str] = []
        for raw in values:
            origin = normalize_origin(raw)
            if origin is None:
                errors.append(f'"{raw}" is not a valid origin. Use scheme://host[:port] with no path.')
            elif origin not in cleaned:
                cleaned.append(origin)
        if errors:
            raise serializers.ValidationError(errors)
        if len(cleaned) > MAX_ALLOWED_ORIGINS:
            raise serializers.ValidationError(f"Add at most {MAX_ALLOWED_ORIGINS} origins.")
        return cleaned

    def validate_brand_color(self, value: str) -> str:
        return value.lower()


class PublicWidgetConfigSerializer(serializers.Serializer):
    organization_name = serializers.CharField(read_only=True)
    title = serializers.CharField(read_only=True)
    greeting = serializers.CharField(read_only=True)
    brand_color = serializers.CharField(read_only=True)
    position = serializers.CharField(read_only=True)
    ws_url = serializers.CharField(read_only=True)


# Socket frames sent by widget.js


def clean_page_url(value: Any) -> str:
    """page_url is context, not input we act on: keep http(s) URLs, drop anything else
    rather than refusing the visitor's question over it."""
    if not isinstance(value, str) or len(value) > 1000:
        return ""
    try:
        parts = urlsplit(value)
    except ValueError:
        return ""
    return value if parts.scheme in ("http", "https") and parts.netloc else ""


class ChatMessageFrameSerializer(serializers.Serializer):
    client_message_id = serializers.CharField(max_length=64)
    conversation_id = serializers.UUIDField(required=False, allow_null=True, default=None)
    content = serializers.CharField()
    page_url = serializers.JSONField(required=False)

    def validate_content(self, value: str) -> str:
        limit = settings.ASSISTANT_MAX_QUESTION_CHARS
        if len(value) > limit:
            raise serializers.ValidationError(f"Keep questions under {limit} characters.")
        return value

    def validate_page_url(self, value: Any) -> str:
        return clean_page_url(value)


class CancelFrameSerializer(serializers.Serializer):
    message_id = serializers.CharField(max_length=64, required=False, allow_null=True, default=None)


class ResumeFrameSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()


class FeedbackFrameSerializer(serializers.Serializer):
    message_id = serializers.UUIDField()
    rating = serializers.ChoiceField(choices=[1, -1], allow_null=True)
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default="")


class HandoffFrameSerializer(serializers.Serializer):
    conversation_id = serializers.UUIDField()
    email = serializers.EmailField(max_length=254)
    name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    note = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
