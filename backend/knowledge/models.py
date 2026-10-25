"""Document library and the retrieval index.

A Document is one uploaded file. Ingestion extracts its text, splits it into Chunks,
embeds each chunk and stores the vector next to a generated full-text search vector,
so one table serves both halves of hybrid search.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVector, SearchVectorField
from django.db import models
from django.utils.text import get_valid_filename
from pgvector.django import HnswIndex, VectorField

from core.models import OrganizationQuerySet, TimeStampedModel, UUIDModel

# Full-text configuration baked into the generated column. Changing it needs a migration.
SEARCH_CONFIG = "english"


class DocumentStatus(models.TextChoices):
    QUEUED = "queued", "Queued"
    PROCESSING = "processing", "Processing"
    READY = "ready", "Ready"
    FAILED = "failed", "Failed"


class Collection(TimeStampedModel):
    """Optional folder for documents, for example "Billing" or "Shipping"."""

    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="collections"
    )
    name = models.CharField(max_length=120)
    description = models.TextField(blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["organization", "name"], name="knowledge_collection_unique_name"),
        ]

    def __str__(self) -> str:
        return self.name


def document_upload_path(instance: Document, filename: str) -> str:
    return f"documents/{instance.organization_id}/{instance.id}/{get_valid_filename(filename)}"


class Document(TimeStampedModel):
    organization = models.ForeignKey(
        "accounts.Organization", on_delete=models.CASCADE, related_name="documents"
    )
    collection = models.ForeignKey(
        Collection, on_delete=models.SET_NULL, null=True, blank=True, related_name="documents"
    )
    title = models.CharField(max_length=255)
    original_filename = models.CharField(max_length=255)
    file = models.FileField(upload_to=document_upload_path, max_length=500)
    # MIME type confirmed by content sniffing, not the browser supplied header.
    content_type = models.CharField(max_length=100)
    file_size = models.PositiveBigIntegerField()
    checksum = models.CharField(max_length=64, help_text="SHA-256 of the file bytes.")
    status = models.CharField(max_length=12, choices=DocumentStatus.choices, default=DocumentStatus.QUEUED)
    error_message = models.TextField(blank=True)
    extracted_text = models.TextField(blank=True)
    page_count = models.PositiveIntegerField(null=True, blank=True)
    chunk_count = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    tags = ArrayField(models.CharField(max_length=50), default=list, blank=True)
    embedder = models.CharField(max_length=100, blank=True)
    uploaded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    processed_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["organization", "status"], name="knowledge_doc_org_status"),
            models.Index(fields=["organization", "-created_at"], name="knowledge_doc_org_created"),
            GinIndex(fields=["tags"], name="knowledge_doc_tags_gin"),
        ]
        constraints = [
            # The same file uploaded twice would double its weight in retrieval.
            models.UniqueConstraint(
                fields=["organization", "checksum"], name="knowledge_document_unique_checksum"
            ),
        ]

    def __str__(self) -> str:
        return self.title


class Chunk(UUIDModel):
    """A retrievable passage. organization is copied from the document so the vector
    and keyword queries can filter by tenant without a join."""

    organization = models.ForeignKey("accounts.Organization", on_delete=models.CASCADE, related_name="+")
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    ordinal = models.PositiveIntegerField(help_text="Position of the chunk inside its document.")
    text = models.TextField()
    heading = models.CharField(max_length=255, blank=True, help_text="Nearest section heading.")
    page_number = models.PositiveIntegerField(null=True, blank=True)
    location = models.CharField(max_length=120, blank=True, help_text='Human label, e.g. "Page 3".')
    char_start = models.PositiveIntegerField(default=0)
    char_end = models.PositiveIntegerField(default=0)
    token_count = models.PositiveIntegerField(default=0)
    embedding = VectorField(dimensions=settings.EMBEDDING_DIMENSIONS, null=True, blank=True)
    embedder = models.CharField(max_length=100, help_text='Name of the embedder, e.g. "hashing-v1".')
    # Maintained by PostgreSQL itself, so it can never drift from the text.
    search_vector = models.GeneratedField(
        expression=SearchVector("heading", weight="A", config=SEARCH_CONFIG)
        + SearchVector("text", weight="B", config=SEARCH_CONFIG),
        output_field=SearchVectorField(),
        db_persist=True,
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["document", "ordinal"]
        indexes = [
            HnswIndex(
                name="knowledge_chunk_embedding_hnsw",
                fields=["embedding"],
                m=16,
                ef_construction=64,
                opclasses=["vector_cosine_ops"],
            ),
            GinIndex(fields=["search_vector"], name="knowledge_chunk_search_gin"),
            models.Index(fields=["organization", "document"], name="knowledge_chunk_org_doc"),
        ]
        constraints = [
            models.UniqueConstraint(fields=["document", "ordinal"], name="knowledge_chunk_unique_ordinal"),
        ]

    def __str__(self) -> str:
        return f"{self.document_id} #{self.ordinal}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if not self.organization_id and self.document_id:
            self.organization_id = self.document.organization_id
        super().save(*args, **kwargs)
