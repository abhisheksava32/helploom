"""Document library and ingestion. Owner: backend-ai.

Entry points:

    accept_uploads(organization, files, ...)  validate, store and queue a batch of uploads
    ingest_document(document_id, trigger)     extract, chunk, embed and index one document
    reindex_document / delete_document / update_document
    document_queryset / tag_counts / document_text      library queries for the views
    collection services                                  CRUD for collections
    reembed_documents(...)                     move ready documents to the active embedder

Retrieval itself lives in assistant.retrieval, which reads knowledge.Chunk.

Ingestion runs off the request path through core.background (a thread pool locally,
Celery when a broker is configured) and publishes a document.status event at every
status change, so the dashboard library updates live.
"""

from __future__ import annotations

import hashlib
import io
import logging
import re
import time
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from datetime import timedelta
from functools import partial
from pathlib import PurePath
from typing import TYPE_CHECKING, Any
from uuid import UUID

from django.conf import settings
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import UploadedFile
from django.db import IntegrityError, connection, transaction
from django.db.models import Count, Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import status
from rest_framework.exceptions import APIException, ValidationError

from billing.services import ensure_document_quota
from core.background import run_in_background
from core.exceptions import Conflict
from core.realtime import broadcast_org_event

from . import extractors
from .chunking import chunk_extraction
from .embeddings import Embedder, EmbeddingError, embed_in_batches, embedding_input, get_embedder
from .extractors import ExtractionError
from .models import (
    Chunk,
    Collection,
    Document,
    DocumentStatus,
    IngestionJob,
    IngestionStatus,
    IngestionTrigger,
)

if TYPE_CHECKING:
    from accounts.models import Organization, User

logger = logging.getLogger(__name__)

# A queued or processing document untouched for this long is assumed lost (for
# example the in-process queue died with a restart) and may be queued again.
STUCK_AFTER = timedelta(minutes=15)
PREVIEW_MAX_CHARS = 200_000
MAX_TAGS = 10
MAX_TAG_LENGTH = 50
# A DOCX is a ZIP; refusing absurd expansion ratios keeps a small upload from
# exhausting memory when python-docx inflates it.
MAX_DOCX_EXPANDED_BYTES = 100 * 1024 * 1024
DOCUMENT_ORDERING = {"created_at", "title", "file_size", "chunk_count", "status"}

GENERIC_FAILURE = "Something went wrong while processing this file. Try re-indexing it."
EMBEDDER_FAILURE = "The embedding service is unavailable right now. Try re-indexing in a few minutes."
MISSING_FILE = "The stored file is missing. Delete this document and upload it again."


class UploadRejected(APIException):
    """No file in the request was accepted; details.rejected says why for each."""

    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "upload_rejected"
    default_detail = "None of the files could be added."

    def __init__(self, rejected: list[dict[str, str]]) -> None:
        super().__init__(detail=self.default_detail, code=self.default_code)
        self.details = {"rejected": rejected}


class FileRejected(Exception):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass
class UploadResult:
    documents: list[Document] = field(default_factory=list)
    rejected: list[dict[str, str]] = field(default_factory=list)


# Realtime


def document_event(document: Document) -> dict[str, Any]:
    from .serializers import DocumentSerializer

    return {"type": "document.status", "document": DocumentSerializer(document).data}


def broadcast_document(document: Document) -> None:
    broadcast_org_event(document.organization_id, document_event(document))


def _reload(document_id: UUID | str) -> Document | None:
    return Document.objects.select_related("collection", "uploaded_by").filter(pk=document_id).first()


# Upload validation


def _unsupported(filename: str) -> FileRejected:
    return FileRejected(
        "unsupported_file_type", f"{filename} is not a PDF, DOCX, Markdown, TXT or HTML file."
    )


def _is_docx(data: bytes, filename: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            info = archive.getinfo("word/document.xml")
            expanded = sum(item.file_size for item in archive.infolist())
    except (zipfile.BadZipFile, KeyError):
        return False
    if info.file_size > MAX_DOCX_EXPANDED_BYTES or expanded > MAX_DOCX_EXPANDED_BYTES * 2:
        raise FileRejected("file_too_large", f"{filename} expands to more than we can safely open.")
    return True


def sniff_content_type(filename: str, data: bytes) -> str:
    """Decide the type from the bytes; the extension must agree. The browser's
    Content-Type header is never trusted."""
    extension = PurePath(filename).suffix.lower().lstrip(".")
    expected = settings.ALLOWED_DOCUMENT_TYPES.get(extension)
    if expected is None:
        raise _unsupported(filename)

    if data.startswith(b"%PDF-"):
        detected = extractors.PDF
    elif data.startswith(b"PK\x03\x04"):
        detected = extractors.DOCX if _is_docx(data, filename) else ""
    else:
        detected = "text"

    if expected in (extractors.PDF, extractors.DOCX):
        if detected != expected:
            raise _unsupported(filename)
        return expected
    if detected != "text":
        raise _unsupported(filename)
    if b"\x00" in data:
        raise _unsupported(filename)
    try:
        data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise FileRejected(
            "unsupported_file_type", f"{filename} is not UTF-8 text. Save it as UTF-8 and upload it again."
        ) from exc
    return expected


def _clean_filename(name: str) -> str:
    base = PurePath(name.replace("\\", "/")).name.strip()
    return base[:255] or "document"


def title_from_filename(filename: str) -> str:
    """ "refund-policy.pdf" becomes "Refund policy": titles appear in citations and in
    the passages the model reads, so they should read like names, not file names."""
    stem = PurePath(filename).stem
    words = re.sub(r"[-_.\s]+", " ", stem).strip()
    if not words:
        return filename[:255]
    if words == words.lower():
        words = words[0].upper() + words[1:]
    return words[:255]


def _storage_name(filename: str) -> str:
    path = PurePath(filename)
    stem = slugify(path.stem)[:100] or "document"
    return f"{stem}{path.suffix.lower()[:10]}"


def normalize_tags(tags: Iterable[str]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        value = tag.strip().lower()
        if value and value not in cleaned:
            cleaned.append(value)
    if len(cleaned) > MAX_TAGS:
        raise ValidationError({"tags": [f"Use at most {MAX_TAGS} tags."]})
    if any(len(tag) > MAX_TAG_LENGTH for tag in cleaned):
        raise ValidationError({"tags": [f"Tags can be at most {MAX_TAG_LENGTH} characters."]})
    return cleaned


def get_collection(organization: Organization, collection_id: UUID | str | None) -> Collection | None:
    if collection_id is None:
        return None
    collection = Collection.objects.for_organization(organization).filter(pk=collection_id).first()
    if collection is None:
        raise ValidationError({"collection_id": ["Unknown collection."]})
    return collection


def create_document(
    organization: Organization,
    *,
    filename: str,
    data: bytes,
    uploaded_by: User | None = None,
    collection: Collection | None = None,
    tags: Sequence[str] = (),
) -> Document:
    """Validate and store one file as a queued Document. Raises FileRejected.

    Does not queue ingestion; callers decide whether to run it in the background
    (uploads) or inline (the eval harness).
    """
    filename = _clean_filename(filename)
    if not data:
        raise FileRejected("empty_file", f"{filename} is empty.")
    if len(data) > settings.MAX_UPLOAD_BYTES:
        raise FileRejected("file_too_large", f"{filename} is larger than {settings.MAX_UPLOAD_MB} MB.")
    content_type = sniff_content_type(filename, data)
    checksum = hashlib.sha256(data).hexdigest()

    existing = Document.objects.for_organization(organization).filter(checksum=checksum).first()
    if existing is not None:
        raise FileRejected(
            "duplicate_document", f'{filename} is already in your library as "{existing.title}".'
        )

    document = Document(
        organization=organization,
        collection=collection,
        title=title_from_filename(filename),
        original_filename=filename,
        content_type=content_type,
        file_size=len(data),
        checksum=checksum,
        tags=list(tags),
        uploaded_by=uploaded_by,
    )
    document.file.save(_storage_name(filename), ContentFile(data), save=False)
    try:
        with transaction.atomic():
            document.save()
    except IntegrityError as exc:
        # Two uploads of the same file raced past the duplicate check.
        document.file.delete(save=False)
        raise FileRejected("duplicate_document", f"{filename} is already in your library.") from exc
    return document


def accept_uploads(
    organization: Organization,
    files: Sequence[UploadedFile],
    *,
    uploaded_by: User | None = None,
    collection_id: UUID | str | None = None,
    tags: Sequence[str] = (),
) -> UploadResult:
    """Store every acceptable file and queue it for ingestion.

    The plan limit is checked against the number of files sent before anything is
    stored, so a batch never half lands over the limit. Each file is then judged on
    its own; one bad file does not reject the others.
    """
    collection = get_collection(organization, collection_id)
    ensure_document_quota(organization, adding=len(files))
    result = UploadResult()
    for upload in files:
        filename = _clean_filename(upload.name or "document")
        try:
            if upload.size is not None and upload.size > settings.MAX_UPLOAD_BYTES:
                # Checked before reading so an oversized file is never pulled into memory.
                raise FileRejected(
                    "file_too_large", f"{filename} is larger than {settings.MAX_UPLOAD_MB} MB."
                )
            data = upload.read()
            document = create_document(
                organization,
                filename=filename,
                data=data,
                uploaded_by=uploaded_by,
                collection=collection,
                tags=tags,
            )
        except FileRejected as rejection:
            result.rejected.append(
                {"filename": filename, "code": rejection.code, "message": rejection.message}
            )
            continue
        result.documents.append(document)

    if not result.documents:
        raise UploadRejected(result.rejected)
    for document in result.documents:
        transaction.on_commit(partial(broadcast_document, document))
        queue_ingestion(document, IngestionTrigger.UPLOAD)
    return result


# Ingestion


def queue_ingestion(document: Document, trigger: str = IngestionTrigger.UPLOAD) -> None:
    from .tasks import ingest_document_task

    run_in_background(ingest_document_task, str(document.id), str(trigger))


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _mark_processing(document: Document) -> None:
    now = timezone.now()
    Document.objects.filter(pk=document.pk).update(
        status=DocumentStatus.PROCESSING, error_message="", updated_at=now
    )
    document.status, document.error_message, document.updated_at = DocumentStatus.PROCESSING, "", now
    broadcast_document(document)


def _mark_failed(document: Document, job: IngestionJob, message: str, started: float) -> None:
    now = timezone.now()
    updated = Document.objects.filter(pk=document.pk).update(
        status=DocumentStatus.FAILED, error_message=message, updated_at=now
    )
    IngestionJob.objects.filter(pk=job.pk).update(
        status=IngestionStatus.FAILED,
        error_message=message,
        finished_at=now,
        duration_ms=_elapsed_ms(started),
        updated_at=now,
    )
    if updated:
        refreshed = _reload(document.pk)
        if refreshed is not None:
            broadcast_document(refreshed)


def ingest_document(document_id: UUID | str, trigger: str = IngestionTrigger.UPLOAD) -> None:
    """Extract, chunk, embed and index one document.

    Never raises: every failure ends with status "failed" and a friendly reason on the
    document (the traceback goes to the log), because nobody is waiting on this call.
    """
    document = _reload(document_id)
    if document is None:
        logger.info("Document %s was deleted before ingestion started", document_id)
        return
    started = time.monotonic()
    job = IngestionJob.objects.create(
        organization_id=document.organization_id, document=document, trigger=trigger
    )
    _mark_processing(document)

    try:
        with document.file.open("rb") as handle:
            data = handle.read()
        extraction = extractors.extract(data, document.content_type)
        drafts = chunk_extraction(extraction)
        if not drafts:
            raise ExtractionError("This file has no readable text.")
        extract_ms = _elapsed_ms(started)

        embed_started = time.monotonic()
        embedder = get_embedder()
        vectors = embed_in_batches(
            embedder, [embedding_input(document.title, draft.heading, draft.text) for draft in drafts]
        )
        embed_ms = _elapsed_ms(embed_started)

        with transaction.atomic():
            locked = Document.objects.select_for_update().filter(pk=document.pk).first()
            if locked is None:
                logger.info("Document %s was deleted during ingestion", document.pk)
                return
            # Old and new chunks swap in one transaction, so search never sees a half
            # indexed document.
            Chunk.objects.filter(document=locked).delete()
            Chunk.objects.bulk_create(
                [
                    Chunk(
                        organization_id=locked.organization_id,
                        document=locked,
                        ordinal=draft.ordinal,
                        text=draft.text,
                        heading=draft.heading,
                        page_number=draft.page_number,
                        location=draft.location,
                        char_start=draft.char_start,
                        char_end=draft.char_end,
                        token_count=draft.token_count,
                        embedding=vector,
                        embedder=embedder.name,
                    )
                    for draft, vector in zip(drafts, vectors, strict=True)
                ],
                batch_size=500,
            )
            now = timezone.now()
            locked.status = DocumentStatus.READY
            locked.error_message = ""
            locked.extracted_text = extraction.text
            locked.page_count = extraction.page_count
            locked.chunk_count = len(drafts)
            locked.token_count = sum(draft.token_count for draft in drafts)
            locked.embedder = embedder.name
            locked.processed_at = now
            locked.save(
                update_fields=[
                    "status", "error_message", "extracted_text", "page_count", "chunk_count",
                    "token_count", "embedder", "processed_at", "updated_at",
                ]
            )  # fmt: skip
            IngestionJob.objects.filter(pk=job.pk).update(
                status=IngestionStatus.SUCCEEDED,
                embedder=embedder.name,
                chunk_count=len(drafts),
                extract_ms=extract_ms,
                embed_ms=embed_ms,
                duration_ms=_elapsed_ms(started),
                finished_at=now,
                updated_at=now,
            )
    except ExtractionError as exc:
        logger.info("Document %s could not be extracted: %s", document.pk, exc)
        _mark_failed(document, job, str(exc), started)
        return
    except EmbeddingError:
        logger.warning("Embedding failed for document %s", document.pk, exc_info=True)
        _mark_failed(document, job, EMBEDDER_FAILURE, started)
        return
    except FileNotFoundError:
        logger.error("Stored file for document %s is missing", document.pk)
        _mark_failed(document, job, MISSING_FILE, started)
        return
    except Exception:
        logger.exception("Ingestion failed for document %s", document.pk)
        _mark_failed(document, job, GENERIC_FAILURE, started)
        return

    refreshed = _reload(document.pk)
    if refreshed is not None:
        broadcast_document(refreshed)


def is_stuck(document: Document) -> bool:
    return document.updated_at < timezone.now() - STUCK_AFTER


def reindex_document(document: Document) -> Document:
    """Queue a fresh extract, chunk and embed run with the current embedder."""
    if document.status in (DocumentStatus.QUEUED, DocumentStatus.PROCESSING) and not is_stuck(document):
        raise Conflict(
            "This document is already being processed. Try again when it finishes.", code="document_busy"
        )
    now = timezone.now()
    Document.objects.filter(pk=document.pk).update(
        status=DocumentStatus.QUEUED, error_message="", updated_at=now
    )
    document.status, document.error_message, document.updated_at = DocumentStatus.QUEUED, "", now
    transaction.on_commit(lambda: broadcast_document(document))
    queue_ingestion(document, IngestionTrigger.REINDEX)
    return document


def delete_document(document: Document) -> None:
    """Delete the row, its chunks and vectors, then the stored file.

    Citations keep their copied title and snippet (their foreign keys are SET_NULL),
    so conversation history stays readable.
    """
    organization_id, document_id = document.organization_id, str(document.pk)
    storage, name = document.file.storage, document.file.name
    with transaction.atomic():
        document.delete()

        def after_commit() -> None:
            if name:
                try:
                    storage.delete(name)
                except OSError:
                    logger.warning("Could not delete stored file %s", name, exc_info=True)
            broadcast_org_event(organization_id, {"type": "document.deleted", "document_id": document_id})

        transaction.on_commit(after_commit)


_UNSET: Any = object()


def update_document(
    document: Document,
    *,
    title: str | None = None,
    tags: Sequence[str] | None = None,
    collection_id: UUID | str | None = _UNSET,
) -> Document:
    fields: list[str] = []
    if title is not None:
        document.title = title.strip()[:255]
        fields.append("title")
    if tags is not None:
        document.tags = normalize_tags(tags)
        fields.append("tags")
    if collection_id is not _UNSET:
        document.collection = get_collection(document.organization, collection_id)
        fields.append("collection")
    if fields:
        document.save(update_fields=[*fields, "updated_at"])
        transaction.on_commit(lambda: broadcast_document(document))
    return document


# Library queries


def document_queryset(
    organization: Organization,
    *,
    status: str | None = None,
    collection: str | None = None,
    tag: str | None = None,
    search: str | None = None,
    ordering: str | None = None,
) -> QuerySet[Document]:
    queryset = Document.objects.for_organization(organization).select_related("collection", "uploaded_by")
    if status:
        queryset = queryset.filter(status=status)
    if collection == "none":
        queryset = queryset.filter(collection__isnull=True)
    elif collection:
        queryset = queryset.filter(collection_id=collection)
    if tag:
        queryset = queryset.filter(tags__contains=[tag.strip().lower()])
    if search:
        queryset = queryset.filter(Q(title__icontains=search) | Q(original_filename__icontains=search))
    field_name = (ordering or "").lstrip("-")
    order = ordering if ordering and field_name in DOCUMENT_ORDERING else "-created_at"
    return queryset.order_by(order, "id")


def tag_counts(organization: Organization) -> list[dict[str, Any]]:
    """Every tag in use with its document count, most used first."""
    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT tag, COUNT(*) AS count
            FROM knowledge_document, unnest(tags) AS tag
            WHERE organization_id = %s
            GROUP BY tag
            ORDER BY count DESC, tag ASC
            """,
            [organization.pk],
        )
        return [{"tag": tag, "count": count} for tag, count in cursor.fetchall()]


def document_text(document: Document) -> dict[str, Any]:
    text = document.extracted_text
    return {
        "document_id": document.pk,
        "title": document.title,
        "text": text[:PREVIEW_MAX_CHARS],
        "char_count": len(text),
        "truncated": len(text) > PREVIEW_MAX_CHARS,
    }


def document_chunks(document: Document) -> QuerySet[Chunk]:
    return (
        Chunk.objects.for_organization(document.organization_id).filter(document=document).order_by("ordinal")
    )


def stale_document_count(organization: Organization | UUID | str, embedder_name: str) -> int:
    """Ready documents whose chunks came from another embedder (run manage.py reembed)."""
    return (
        Document.objects.for_organization(organization)
        .filter(status=DocumentStatus.READY)
        .exclude(embedder=embedder_name)
        .count()
    )


# Collections


def collection_queryset(organization: Organization, *, search: str | None = None) -> QuerySet[Collection]:
    queryset = Collection.objects.for_organization(organization).annotate(document_count=Count("documents"))
    if search:
        queryset = queryset.filter(name__icontains=search)
    return queryset.order_by("name", "id")


def _ensure_unique_collection_name(
    organization: Organization, name: str, exclude: Collection | None = None
) -> None:
    clash = Collection.objects.for_organization(organization).filter(name__iexact=name)
    if exclude is not None:
        clash = clash.exclude(pk=exclude.pk)
    if clash.exists():
        raise ValidationError({"name": ["A collection with this name already exists."]})


def _with_count(collection: Collection) -> Collection:
    return collection_queryset(collection.organization).get(pk=collection.pk)


def create_collection(organization: Organization, *, name: str, description: str = "") -> Collection:
    name = name.strip()
    _ensure_unique_collection_name(organization, name)
    try:
        with transaction.atomic():
            collection = Collection.objects.create(
                organization=organization, name=name, description=description
            )
    except IntegrityError as exc:
        raise ValidationError({"name": ["A collection with this name already exists."]}) from exc
    return _with_count(collection)


def update_collection(
    collection: Collection, *, name: str | None = None, description: str | None = None
) -> Collection:
    if name is not None:
        name = name.strip()
        _ensure_unique_collection_name(collection.organization, name, exclude=collection)
        collection.name = name
    if description is not None:
        collection.description = description
    try:
        with transaction.atomic():
            collection.save()
    except IntegrityError as exc:
        raise ValidationError({"name": ["A collection with this name already exists."]}) from exc
    return _with_count(collection)


def delete_collection(collection: Collection) -> None:
    # Documents keep existing and lose their collection (on_delete=SET_NULL).
    collection.delete()


# Re-embedding


@dataclass
class ReembedReport:
    embedder: str
    documents: int = 0
    chunks: int = 0
    failed: list[str] = field(default_factory=list)


def reembed_documents(
    *,
    organization_id: UUID | str | None = None,
    force: bool = False,
    embedder: Embedder | None = None,
) -> ReembedReport:
    """Re-embed stored chunks with the active embedder, without re-extracting files.

    Only ready documents whose embedder differs are touched unless force is set.
    Each document is swapped in its own transaction, so a long run can be interrupted
    and resumed safely.
    """
    embedder = embedder or get_embedder()
    report = ReembedReport(embedder=embedder.name)
    documents = Document.objects.filter(status=DocumentStatus.READY).order_by("created_at")
    if organization_id is not None:
        documents = documents.filter(organization_id=organization_id)
    if not force:
        documents = documents.exclude(embedder=embedder.name)

    for document in documents.iterator(chunk_size=100):
        started = time.monotonic()
        chunks = list(Chunk.objects.filter(document=document).order_by("ordinal"))
        try:
            vectors = embed_in_batches(
                embedder, [embedding_input(document.title, chunk.heading, chunk.text) for chunk in chunks]
            )
        except EmbeddingError:
            logger.warning("Re-embedding failed for document %s", document.pk, exc_info=True)
            report.failed.append(str(document.pk))
            continue
        with transaction.atomic():
            for chunk, vector in zip(chunks, vectors, strict=True):
                chunk.embedding = vector
                chunk.embedder = embedder.name
            Chunk.objects.bulk_update(chunks, ["embedding", "embedder"], batch_size=500)
            document.embedder = embedder.name
            document.save(update_fields=["embedder", "updated_at"])
            now = timezone.now()
            IngestionJob.objects.create(
                organization_id=document.organization_id,
                document=document,
                trigger=IngestionTrigger.REEMBED,
                status=IngestionStatus.SUCCEEDED,
                embedder=embedder.name,
                chunk_count=len(chunks),
                embed_ms=_elapsed_ms(started),
                duration_ms=_elapsed_ms(started),
                finished_at=now,
            )
        report.documents += 1
        report.chunks += len(chunks)
    return report
