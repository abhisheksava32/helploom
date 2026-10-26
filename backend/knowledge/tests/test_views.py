"""The Documents and Collections endpoints in docs/API.md, including tenant isolation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, Organization
from core.testing import access_token_for
from knowledge.models import Collection, Document, DocumentStatus

from .factories import REFUND_POLICY, SHIPPING_FAQ, ingest, upload

pytestmark = pytest.mark.django_db

DOCUMENT_FIELDS = {
    "id", "title", "original_filename", "content_type", "file_size", "status", "error_message",
    "page_count", "chunk_count", "token_count", "tags", "collection", "embedder", "uploaded_by",
    "created_at", "updated_at", "processed_at",
}  # fmt: skip


def client_for(membership: Membership) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(membership.user)}",
        HTTP_X_ORGANIZATION_ID=str(membership.organization_id),
    )
    return client


@pytest.fixture
def agent_client(organization: Organization, make_member: Callable[..., Membership]) -> APIClient:
    return client_for(make_member(organization=organization, role="agent"))


@pytest.fixture
def other_org_document(make_member: Callable[..., Membership]) -> Document:
    other = make_member().organization
    return ingest(other, "theirs.md", "# Their secret policy\n\nOnly for them.")


def test_upload_returns_documents_and_per_file_rejections(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/documents/",
        {
            "files": [upload("refunds.md", REFUND_POLICY), upload("logo.png", b"\x89PNG")],
            "tags": "Billing, policy",
        },
        format="multipart",
    )

    assert response.status_code == 201, response.json()
    body = response.json()
    assert len(body["documents"]) == 1
    document = body["documents"][0]
    assert set(document) == DOCUMENT_FIELDS
    # The response describes the upload as accepted; ingestion reports progress live.
    assert document["status"] == "queued"
    assert Document.objects.get(pk=document["id"]).status == DocumentStatus.READY
    assert document["tags"] == ["billing", "policy"]
    assert document["uploaded_by"]["email"]
    assert body["rejected"] == [
        {
            "filename": "logo.png",
            "code": "unsupported_file_type",
            "message": "logo.png is not a PDF, DOCX, Markdown, TXT or HTML file.",
        }
    ]


def test_upload_with_nothing_acceptable_is_a_400(auth_client: APIClient) -> None:
    response = auth_client.post(
        "/api/v1/documents/", {"files": [upload("x.png", b"\x89PNG")]}, format="multipart"
    )

    assert response.status_code == 400
    error = response.json()["error"]
    assert error["code"] == "upload_rejected"
    assert error["details"]["rejected"][0]["code"] == "unsupported_file_type"


def test_upload_needs_files(auth_client: APIClient) -> None:
    response = auth_client.post("/api/v1/documents/", {}, format="multipart")

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "validation_error"


def test_upload_into_an_unknown_collection_is_a_validation_error(
    auth_client: APIClient, make_organization: Callable[..., Organization]
) -> None:
    foreign = Collection.objects.create(organization=make_organization(), name="Theirs")

    response = auth_client.post(
        "/api/v1/documents/",
        {"files": [upload("refunds.md", REFUND_POLICY)], "collection_id": str(foreign.id)},
        format="multipart",
    )

    assert response.status_code == 400
    assert "collection_id" in response.json()["error"]["details"]


def test_agents_can_read_but_not_upload(agent_client: APIClient, organization: Organization) -> None:
    ingest(organization, "refunds.md", REFUND_POLICY)

    assert agent_client.get("/api/v1/documents/").status_code == 200
    response = agent_client.post(
        "/api/v1/documents/", {"files": [upload("a.md", "# A\n\nB.")]}, format="multipart"
    )
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "insufficient_role"


def test_list_is_paginated_filtered_and_isolated(
    auth_client: APIClient, organization: Organization, other_org_document: Document
) -> None:
    billing = Collection.objects.create(organization=organization, name="Billing")
    ingest(organization, "refunds.md", REFUND_POLICY, tags=["billing"], collection=billing)
    ingest(organization, "shipping.md", SHIPPING_FAQ)

    everything = auth_client.get("/api/v1/documents/?ordering=title").json()
    assert everything["count"] == 2
    assert [d["title"] for d in everything["results"]] == ["Refunds", "Shipping"]
    assert other_org_document.title not in {d["title"] for d in everything["results"]}

    assert auth_client.get("/api/v1/documents/?tag=billing").json()["count"] == 1
    assert auth_client.get(f"/api/v1/documents/?collection={billing.id}").json()["count"] == 1
    assert auth_client.get("/api/v1/documents/?collection=none").json()["results"][0]["title"] == "Shipping"
    assert auth_client.get("/api/v1/documents/?search=SHIP").json()["count"] == 1
    assert auth_client.get("/api/v1/documents/?status=failed").json()["count"] == 0
    assert auth_client.get("/api/v1/documents/?page_size=1").json()["next"] is not None
    assert auth_client.get("/api/v1/documents/?ordering=unknown").status_code == 200
    assert auth_client.get("/api/v1/documents/?status=bogus").status_code == 400


def test_other_organizations_documents_are_404(auth_client: APIClient, other_org_document: Document) -> None:
    base = f"/api/v1/documents/{other_org_document.id}/"

    for response in (
        auth_client.get(base),
        auth_client.patch(base, {"title": "mine now"}),
        auth_client.delete(base),
        auth_client.post(f"{base}reindex/"),
        auth_client.get(f"{base}text/"),
        auth_client.get(f"{base}chunks/"),
    ):
        assert response.status_code == 404
        assert response.json()["error"]["code"] == "not_found"
    assert Document.objects.filter(pk=other_org_document.pk, title="Theirs").exists()


def test_detail_patch_and_delete(auth_client: APIClient, organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    collection = Collection.objects.create(organization=organization, name="Billing")
    url = f"/api/v1/documents/{document.id}/"

    assert auth_client.get(url).json()["chunk_count"] == document.chunk_count

    patched = auth_client.patch(
        url, {"title": "Refunds", "tags": ["Policy"], "collection_id": str(collection.id)}
    )
    assert patched.status_code == 200
    assert (patched.json()["title"], patched.json()["tags"]) == ("Refunds", ["policy"])
    assert patched.json()["collection"] == {"id": str(collection.id), "name": "Billing"}

    assert auth_client.patch(url, {"collection_id": None}).json()["collection"] is None
    assert auth_client.delete(url).status_code == 204
    assert not Document.objects.filter(pk=document.pk).exists()


def test_reindex_is_accepted_or_conflicts_while_busy(
    auth_client: APIClient, organization: Organization
) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)
    url = f"/api/v1/documents/{document.id}/reindex/"

    accepted = auth_client.post(url)
    assert accepted.status_code == 202
    assert accepted.json()["status"] == "queued"

    Document.objects.filter(pk=document.pk).update(status=DocumentStatus.PROCESSING)
    busy = auth_client.post(url)
    assert busy.status_code == 409
    assert busy.json()["error"]["code"] == "document_busy"


def test_text_and_chunks(auth_client: APIClient, organization: Organization) -> None:
    document = ingest(organization, "refunds.md", REFUND_POLICY)

    text = auth_client.get(f"/api/v1/documents/{document.id}/text/").json()
    assert text["document_id"] == str(document.id)
    assert text["text"].startswith("Refund policy")
    assert text["truncated"] is False

    chunks = auth_client.get(f"/api/v1/documents/{document.id}/chunks/").json()
    assert chunks["count"] == document.chunk_count
    first = chunks["results"][0]
    assert set(first) == {"id", "ordinal", "heading", "location", "page_number", "token_count", "text"}
    assert first["ordinal"] == 0


def test_tags_endpoint(auth_client: APIClient, organization: Organization) -> None:
    ingest(organization, "refunds.md", REFUND_POLICY, tags=["billing"])

    assert auth_client.get("/api/v1/documents/tags/").json() == {"results": [{"tag": "billing", "count": 1}]}


def test_collections_crud(auth_client: APIClient, organization: Organization) -> None:
    created = auth_client.post("/api/v1/collections/", {"name": "Billing", "description": "Invoices."})
    assert created.status_code == 201
    collection = created.json()
    assert collection["document_count"] == 0

    duplicate = auth_client.post("/api/v1/collections/", {"name": "billing"})
    assert duplicate.status_code == 400
    assert "name" in duplicate.json()["error"]["details"]

    ingest(organization, "refunds.md", REFUND_POLICY, collection=Collection.objects.get(pk=collection["id"]))
    listed = auth_client.get("/api/v1/collections/").json()
    assert listed["results"][0]["document_count"] == 1

    url = f"/api/v1/collections/{collection['id']}/"
    assert auth_client.patch(url, {"description": "Money matters."}).json()["description"] == "Money matters."
    assert auth_client.delete(url).status_code == 204
    # Documents stay and lose their collection.
    assert Document.objects.get(title="Refunds").collection is None


def test_collections_are_isolated(
    auth_client: APIClient, make_organization: Callable[..., Organization]
) -> None:
    foreign = Collection.objects.create(organization=make_organization(), name="Theirs")

    assert auth_client.get("/api/v1/collections/").json()["count"] == 0
    assert auth_client.patch(f"/api/v1/collections/{foreign.id}/", {"name": "x"}).status_code == 404


def test_requires_authentication(api_client: Any) -> None:
    response = api_client.get("/api/v1/documents/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"
