"""Serializers for documents, uploads, collections, chunks and text previews.

Field names follow docs/API.md, section "Documents". Every output
field is listed explicitly so a column added later can never leak through the API.
"""

from __future__ import annotations

from django.conf import settings
from rest_framework import serializers

from .models import Chunk, Collection, Document, DocumentStatus
from .services import DOCUMENT_ORDERING, MAX_TAG_LENGTH, MAX_TAGS, normalize_tags


class UserRefSerializer(serializers.Serializer):
    """docs/API.md UserRef: a user as it appears inside other objects."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class CollectionRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class DocumentSerializer(serializers.ModelSerializer):
    collection = CollectionRefSerializer(read_only=True, allow_null=True)
    uploaded_by = UserRefSerializer(read_only=True, allow_null=True)

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "original_filename",
            "content_type",
            "file_size",
            "status",
            "error_message",
            "page_count",
            "chunk_count",
            "token_count",
            "tags",
            "collection",
            "embedder",
            "uploaded_by",
            "created_at",
            "updated_at",
            "processed_at",
        ]
        read_only_fields = fields


def _split_tags(value: str) -> list[str]:
    return [part for part in value.split(",") if part.strip()]


class DocumentUploadSerializer(serializers.Serializer):
    files = serializers.ListField(
        child=serializers.FileField(allow_empty_file=True, use_url=False),
        allow_empty=False,
        max_length=settings.MAX_FILES_PER_UPLOAD,
        error_messages={
            "empty": "Choose at least one file to upload.",
            "max_length": f"Upload at most {settings.MAX_FILES_PER_UPLOAD} files at a time.",
        },
    )
    collection_id = serializers.UUIDField(required=False, allow_null=True)
    tags = serializers.CharField(required=False, allow_blank=True, max_length=MAX_TAGS * (MAX_TAG_LENGTH + 2))

    def validate_tags(self, value: str) -> list[str]:
        return normalize_tags(_split_tags(value))


class DocumentUpdateSerializer(serializers.Serializer):
    title = serializers.CharField(required=False, min_length=1, max_length=255, trim_whitespace=True)
    tags = serializers.ListField(
        child=serializers.CharField(max_length=MAX_TAG_LENGTH, allow_blank=False),
        required=False,
        max_length=MAX_TAGS,
    )
    collection_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_tags(self, value: list[str]) -> list[str]:
        return normalize_tags(value)


class DocumentListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=DocumentStatus.choices, required=False)
    collection = serializers.CharField(required=False)
    tag = serializers.CharField(required=False, max_length=MAX_TAG_LENGTH)
    search = serializers.CharField(required=False, max_length=200)
    ordering = serializers.CharField(required=False)

    def validate_collection(self, value: str) -> str:
        if value == "none":
            return value
        try:
            return str(serializers.UUIDField().to_internal_value(value))
        except serializers.ValidationError as exc:
            raise serializers.ValidationError('Use a collection id or "none".') from exc

    def validate_ordering(self, value: str) -> str | None:
        # Unknown fields fall back to the default rather than erroring (docs/API.md).
        return value if value.lstrip("-") in DOCUMENT_ORDERING else None


class TagCountSerializer(serializers.Serializer):
    tag = serializers.CharField()
    count = serializers.IntegerField()


class DocumentTextSerializer(serializers.Serializer):
    document_id = serializers.UUIDField()
    title = serializers.CharField()
    text = serializers.CharField(allow_blank=True)
    char_count = serializers.IntegerField()
    truncated = serializers.BooleanField()


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "ordinal", "heading", "location", "page_number", "token_count", "text"]
        read_only_fields = fields


class CollectionSerializer(serializers.ModelSerializer):
    document_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Collection
        fields = ["id", "name", "description", "document_count", "created_at"]
        read_only_fields = ["id", "document_count", "created_at"]


class CollectionWriteSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=1, max_length=120, trim_whitespace=True)
    description = serializers.CharField(required=False, allow_blank=True, max_length=1000)


class CollectionListQuerySerializer(serializers.Serializer):
    search = serializers.CharField(required=False, max_length=120)
