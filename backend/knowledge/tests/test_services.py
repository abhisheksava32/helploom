"""Upload validation, the ingestion pipeline, re-indexing, deletion and re-embedding."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import Organization
from core.exceptions import Conflict, PlanLimitExceeded
from evals.samples import make_docx, make_pdf
from knowledge import extractors, services
from knowledge.embeddings import HashingEmbedder
from knowledge.models import Chunk, Collection, Document, DocumentStatus, IngestionJob, IngestionStatus
from knowledge.services import FileRejected, UploadRejected, sniff_content_type

from .factories import REFUND_POLICY, SHIPPING_FAQ, ingest, upload

pytestmark = pytest.mark.django_db


# Type sniffing


def test_sniffing_trusts_bytes_and_requires_a_matching_extension() -> None:
    assert sniff_content_type("policy.pdf", make_pdf([["Hello world."]])) == extractors.PDF
    assert sniff_content_type("guide.docx", make_docx([("p", "Hi")])) == extractors.DOCX
    assert sniff_content_type("faq.md", b"# FAQ") == extractors.MARKDOWN
    assert sniff_content_type("notes.TXT", b"plain") == extractors.TEXT
    assert sniff_content_type("page.htm", b"<p>x</p>") == extractors.HTML


@pytest.mark.parametrize(
    ("filename", "data"),
    [
        ("logo.png", b"\x89PNG\r\n\x1a\n"),
        ("fake.pdf", b"just text pretending to be a pdf"),
        ("fake.docx", b"PK\x03\x04 not a real zip"),
        ("binary.txt", b"abc\x00def"),
        ("guide.md", make_pdf([["A PDF renamed to .md"]])),
        ("noextension", b"text"),
    ],
)
def test_sniffing_rejects_mismatched_or_unsupported_files(filename: str, data: bytes) -> None:
    with pytest.raises(FileRejected) as caught:
        sniff_content_type(filename, data)

    assert caught.value.code == "unsupported_file_type"


@pytest.mark.parametrize(
    ("filename", "title"),
    [
        ("refund-policy.pdf", "Refund policy"),
        ("shipping_and_delivery.md", "Shipping and delivery"),
        ("FAQ 2026.txt", "FAQ 2026"),
        ("Returns.html", "Returns"),
        ("notes.v2.md", "Notes v2"),
    ],
)
def test_titles_are_derived_from_filenames(filename: str, title: str) -> None:
    assert services.title_from_filename(filename) == title


def test_text_files_must_be_utf8() -> None:
    with pytest.raises(FileRejected, match="UTF-8"):
        sniff_content_type("latin.txt", "caf\xe9".encode("latin-1"))


# Uploads


def test_accept_uploads_stores_and_ingests_each_file(organization: Organization, owner: Any) -> None:
    result = services.accept_uploads(
        organization,
        [upload("refund-policy.md", REFUND_POLICY), upload("shipping.md", SHIPPING_FAQ)],
        uploaded_by=owner.user,
        tags=["billing"],
    )

    assert [doc.title for doc in result.documents] == ["Refund policy", "Shipping"]
    assert result.rejected == []
    document = Document.objects.get(title="Refund policy")
    # Tests run background jobs eagerly, so ingestion already finished.
    assert document.status == DocumentStatus.READY
    assert document.content_type == "text/markdown"
    assert document.tags == ["billing"]
    assert document.uploaded_by == owner.user
    assert document.chunk_count == Chunk.objects.filter(document=document).count() > 0
    assert document.embedder == "hashing-v1"
    assert (document.file.name or "").startswith(f"documents/{organization.id}/{document.id}/")


def test_each_file_is_judged_on_its_own(organization: Organization) -> None:
    ingest(organization, "refund-policy.md", REFUND_POLICY)

    result = services.accept_uploads(
        organization,
        [
            upload("again.md", REFUND_POLICY),
            upload("empty.txt", b""),
            upload("logo.png", b"\x89PNG"),
            upload("good.md", SHIPPING_FAQ),
        ],
    )

    assert [doc.original_filename for doc in result.documents] == ["good.md"]
    assert [(r["filename"], r["code"]) for r in result.rejected] == [
        ("again.md", "duplicate_document"),
        ("empty.txt", "empty_file"),
        ("logo.png", "unsupported_file_type"),
    ]
    assert 'already in your library as "Refund policy"' in result.rejected[0]["message"]


def test_oversized_files_are_rejected_before_reading(organization: Organization, settings: Any) -> None:
    settings.MAX_UPLOAD_BYTES = 10

    with pytest.raises(UploadRejected) as caught:
        services.accept_uploads(organization, [upload("big.md", "x" * 50)])

    assert caught.value.details["rejected"][0]["code"] == "file_too_large"


def test_upload_rejected_when_no_file_is_accepted(organization: Organization) -> None:
    with pytest.raises(UploadRejected) as caught:
        services.accept_uploads(organization, [upload("logo.png", b"\x89PNG")])

    assert caught.value.get_codes() == "upload_rejected"
    assert Document.objects.count() == 0


def test_plan_limit_is_checked_before_anything_is_stored(organization: Organization, settings: Any) -> None:
    files = [upload(f"doc{index}.md", f"# Doc {index}\n\nBody {index}.") for index in range(11)]

    with pytest.raises(PlanLimitExceeded) as caught:
        services.accept_uploads(organization, files)

    assert caught.value.details["limit"] == "documents"
    assert Document.objects.count() == 0


def test_uploads_publish_status_events(organization: Organization, broadcasts: list[Any]) -> None:
    services.accept_uploads(organization, [upload("refunds.md", REFUND_POLICY)])

    statuses = [event["document"]["status"] for _, event in broadcasts if event["type"] == "document.status"]
    # "queued" goes out after commit, which the test transaction never reaches.
    assert statuses == ["processing", "ready"]
    assert {org for org, _ in broadcasts} == {str(organization.id)}


# Ingestion


def test_ingestion_records_a_job_and_page_aware_chunks(organization: Organization) -> None:
    pdf = make_pdf([["# Earning Points", "One point per dollar spent."], ["# Expiry", "Points expire."]])

    document = ingest(organization, "rewards.pdf", pdf)

    assert document.status == DocumentStatus.READY
    assert document.page_count == 2
    chunks = list(document.chunks.order_by("ordinal"))
    assert [(c.location, c.page_number) for c in chunks] == [("Page 1", 1), ("Page 2", 2)]
    assert all(c.organization_id == organization.id and c.embedding is not None for c in chunks)
    assert document.extracted_text[chunks[0].char_start : chunks[0].char_end] == chunks[0].text
    job = IngestionJob.objects.get(document=document)
    assert job.status == IngestionStatus.SUCCEEDED
    assert job.chunk_count == 2
    assert job.duration_ms is not None


def test_unreadable_files_fail_with_a_friendly_reason(organization: Organization) -> None:
    document = ingest(organization, "scan.pdf", make_pdf([[]]))

    assert document.status == DocumentStatus.FAILED
    assert document.error_message == "This PDF has no extractable text. It may be a scanned image."
    assert document.chunk_count == 0
    job = IngestionJob.objects.get(document=document)
    assert job.status == IngestionStatus.FAILED
    assert job.error_message == document.error_message


def test_unexpected_errors_never_escape_ingestion(
    organization: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    def explode(*args: Any) -> None:
        raise RuntimeError("boom")

    monkeypatch.setattr(services, "chunk_extraction", explode)

    document = ingest(organization, "refunds.md", REFUND_POLICY)

    assert document.status == DocumentStatus.FAILED
    assert "re-indexing" in document.error_message
    assert "boom" not in document.error_message


def test_reingesting_swaps_chunks_atomically(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    first_ids = set(document.chunks.values_list("id", flat=True))

    services.ingest_document(document.id)

    assert first_ids.isdisjoint(set(document.chunks.values_list("id", flat=True)))
    assert document.chunks.count() == len(first_ids)


def test_ingesting_a_deleted_document_is_a_no_op(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    document_id = document.id
    document.delete()

    services.ingest_document(document_id)

    assert not IngestionJob.objects.filter(document_id=document_id).exists()


# Re-index and delete


def test_reindex_queues_a_fresh_run(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)

    returned = services.reindex_document(document)

    assert returned.status == DocumentStatus.QUEUED
    document.refresh_from_db()
    assert document.status == DocumentStatus.READY  # the eager job already ran
    assert IngestionJob.objects.filter(document=document).count() == 2


def test_reindex_refuses_busy_documents_unless_stuck(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    Document.objects.filter(pk=document.pk).update(
        status=DocumentStatus.PROCESSING, updated_at=timezone.now()
    )
    document.refresh_from_db()

    with pytest.raises(Conflict) as caught:
        services.reindex_document(document)
    assert caught.value.get_codes() == "document_busy"

    Document.objects.filter(pk=document.pk).update(updated_at=timezone.now() - timedelta(minutes=20))
    document.refresh_from_db()
    services.reindex_document(document)
    document.refresh_from_db()
    assert document.status == DocumentStatus.READY


def test_delete_removes_chunks_and_the_stored_file(
    organization: Organization, django_capture_on_commit_callbacks: Callable[..., Any], broadcasts: list[Any]
) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    document_id, storage, name = document.id, document.file.storage, document.file.name or ""
    assert storage.exists(name)

    with django_capture_on_commit_callbacks(execute=True):
        services.delete_document(document)

    assert not Chunk.objects.filter(document_id=document_id).exists()
    assert not storage.exists(name)
    assert broadcasts[-1][1] == {"type": "document.deleted", "document_id": str(document_id)}


def test_update_document_changes_title_tags_and_collection(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    collection = Collection.objects.create(organization=organization, name="Billing")

    services.update_document(
        document, title="  Refunds  ", tags=["Billing", "billing", " Policy "], collection_id=collection.id
    )
    document.refresh_from_db()
    assert (document.title, document.tags, document.collection) == (
        "Refunds",
        ["billing", "policy"],
        collection,
    )

    services.update_document(document, collection_id=None)
    document.refresh_from_db()
    assert document.collection is None


def test_collections_of_other_organizations_are_unknown(
    organization: Organization, make_organization: Callable[..., Organization]
) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    foreign = Collection.objects.create(organization=make_organization(), name="Theirs")

    with pytest.raises(ValidationError):
        services.update_document(document, collection_id=foreign.id)


# Queries


def test_tag_counts_are_most_used_first(organization: Organization) -> None:
    ingest(organization, "a.md", "# A\n\nAlpha.", tags=["billing", "policy"])
    ingest(organization, "b.md", "# B\n\nBeta.", tags=["billing"])

    assert services.tag_counts(organization) == [
        {"tag": "billing", "count": 2},
        {"tag": "policy", "count": 1},
    ]


def test_document_text_is_capped_for_the_preview(
    organization: Organization, monkeypatch: pytest.MonkeyPatch
) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    monkeypatch.setattr(services, "PREVIEW_MAX_CHARS", 10)

    preview = services.document_text(document)

    assert preview["text"] == document.extracted_text[:10]
    assert preview["truncated"] is True
    assert preview["char_count"] == len(document.extracted_text)


def test_collection_names_are_unique_ignoring_case(organization: Organization) -> None:
    services.create_collection(organization, name="Billing")

    with pytest.raises(ValidationError):
        services.create_collection(organization, name="billing")


# Re-embedding


class _OtherEmbedder(HashingEmbedder):
    name = "other-v1"


def test_reembed_moves_stale_documents_to_the_active_embedder(organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    assert services.stale_document_count(organization, "other-v1") == 1

    report = services.reembed_documents(embedder=_OtherEmbedder())

    assert (report.documents, report.chunks) == (1, document.chunk_count)
    document.refresh_from_db()
    assert document.embedder == "other-v1"
    assert set(document.chunks.values_list("embedder", flat=True)) == {"other-v1"}
    assert services.stale_document_count(organization, "other-v1") == 0
    # Up to date documents are skipped unless forced.
    assert services.reembed_documents(embedder=_OtherEmbedder()).documents == 0
    assert services.reembed_documents(embedder=_OtherEmbedder(), force=True).documents == 1
