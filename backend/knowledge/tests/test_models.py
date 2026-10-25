"""The retrieval index: pgvector embeddings and the generated full-text column."""

from __future__ import annotations

import numpy as np
import pytest
from django.contrib.postgres.search import SearchQuery
from pgvector.django import CosineDistance

from accounts.models import Organization
from knowledge.models import Chunk, Document


def _document(organization: Organization, title: str = "Refund policy") -> Document:
    return Document.objects.create(
        organization=organization,
        title=title,
        original_filename="refunds.md",
        file="documents/refunds.md",
        content_type="text/markdown",
        file_size=120,
        checksum=title.lower().replace(" ", "-"),
    )


def _unit(vector: list[float]) -> list[float]:
    padded = np.zeros(768)
    padded[: len(vector)] = vector
    return (padded / np.linalg.norm(padded)).tolist()


@pytest.mark.django_db
def test_chunks_inherit_the_documents_organization(organization: Organization) -> None:
    document = _document(organization)

    chunk = Chunk.objects.create(document=document, ordinal=0, text="Refunds take 5 days.", embedder="test")

    assert chunk.organization_id == organization.id


@pytest.mark.django_db
def test_cosine_search_orders_by_similarity(organization: Organization) -> None:
    document = _document(organization)
    near = Chunk.objects.create(
        document=document, ordinal=0, text="near", embedder="test", embedding=_unit([1.0, 0.1])
    )
    Chunk.objects.create(
        document=document, ordinal=1, text="far", embedder="test", embedding=_unit([0.0, 1.0])
    )

    ranked = Chunk.objects.for_organization(organization).order_by(
        CosineDistance("embedding", _unit([1.0, 0.0]))
    )

    assert ranked.first() == near


@pytest.mark.django_db
def test_search_vector_is_maintained_by_postgres(organization: Organization) -> None:
    document = _document(organization)
    Chunk.objects.create(
        document=document,
        ordinal=0,
        heading="Returns",
        text="Customers can return unused items within 30 days for a full refund.",
        embedder="test",
    )

    query = SearchQuery("refunds", search_type="websearch", config="english")

    assert Chunk.objects.filter(search_vector=query).count() == 1
