"""Hybrid retrieval: both search sides, fusion, diversity, the gate and isolation."""

from __future__ import annotations

import uuid
from collections.abc import Callable
from typing import Any

import numpy as np
import pytest

from accounts.models import Organization
from assistant.retrieval import (
    Passage,
    fuse,
    keyword_terms,
    mmr,
    relevance_threshold,
    resolve_query_embedder,
    search,
)
from knowledge.embeddings import HashingEmbedder
from knowledge.models import Document
from knowledge.tests.factories import REFUND_POLICY, ingest

pytestmark = pytest.mark.django_db


def test_hybrid_search_finds_the_right_passage(knowledge_base: dict[str, Document]) -> None:
    result = search(knowledge_base["refunds"].organization_id, "How long do refunds take?")

    top = result.passages[0]
    assert top.document_id == knowledge_base["refunds"].id
    assert top.heading == "Refund policy > Refund window"
    assert top.vector_rank is not None and top.keyword_rank is not None
    assert result.embedder == "hashing-v1"
    assert result.would_answer
    assert result.top_similarity is not None and 0 < result.top_similarity <= 1


def test_keyword_side_matches_exact_tokens(knowledge_base: dict[str, Document]) -> None:
    result = search(knowledge_base["shipping"].organization_id, "SKU-4471", mode="keyword")

    assert result.passages[0].document_id == knowledge_base["shipping"].id
    assert result.passages[0].similarity is None  # keyword only: no vector similarity
    assert result.top_similarity is None
    assert not result.would_answer  # the gate only trusts vector similarity


def test_vector_mode_reports_similarity_in_rank_order(knowledge_base: dict[str, Document]) -> None:
    result = search(knowledge_base["refunds"].organization_id, "delivery times", mode="vector", use_mmr=False)

    similarities = [p.similarity for p in result.passages if p.similarity is not None]
    assert similarities == sorted(similarities, reverse=True)
    assert result.keyword_hits == 0


def test_search_never_crosses_organizations(
    organization: Organization, make_organization: Callable[..., Organization]
) -> None:
    other = make_organization()
    theirs = ingest(other, "refunds.md", REFUND_POLICY)

    mine = search(organization.id, "How long do refunds take?")
    assert mine.passages == []
    assert mine.top_similarity is None
    assert not mine.would_answer

    ingest(organization, "refunds.md", REFUND_POLICY)
    results = search(organization.id, "How long do refunds take?", top_k=20).passages
    assert results
    assert theirs.id not in {p.document_id for p in results}


def test_irrelevant_questions_fall_below_the_threshold(knowledge_base: dict[str, Document]) -> None:
    result = search(knowledge_base["refunds"].organization_id, "Who won the football world cup in 2014?")

    assert not result.would_answer
    assert result.threshold == HashingEmbedder.default_threshold


def test_threshold_setting_overrides_the_embedder_default(settings: Any) -> None:
    settings.RELEVANCE_THRESHOLD = 0.42

    assert relevance_threshold(HashingEmbedder()) == 0.42


def test_keyword_terms_cannot_inject_query_syntax() -> None:
    assert keyword_terms('refund -"policy" OR or and SKU-4471!') == "refund or policy or sku or 4471"
    assert keyword_terms("?!") == ""


def _row(chunk_id: uuid.UUID, distance: float = 0.5) -> dict[str, Any]:
    return {
        "id": chunk_id,
        "document_id": uuid.uuid4(),
        "document__title": "Doc",
        "ordinal": 0,
        "location": "",
        "heading": "",
        "text": "text",
        "page_number": None,
        "embedding": None,
        "distance": distance,
    }


def test_reciprocal_rank_fusion_rewards_agreement() -> None:
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()

    fused = fuse([_row(a, 0.1), _row(b, 0.2)], [_row(b), _row(c)], k=60)

    assert [p.chunk_id for p in fused] == [b, a, c]
    assert fused[0].score == pytest.approx(1 / 62 + 1 / 61)
    assert fused[1].score == pytest.approx(1 / 61)
    assert (fused[0].vector_rank, fused[0].keyword_rank) == (2, 1)
    assert fused[2].similarity is None


def _passage(score: float, vector: list[float]) -> Passage:
    embedding = np.array(vector) / np.linalg.norm(vector)
    return Passage(uuid.uuid4(), uuid.uuid4(), "Doc", "", "", "text", score=score, embedding=embedding)


def test_mmr_prefers_a_distinct_passage_over_a_near_duplicate() -> None:
    best = _passage(0.030, [1.0, 0.0])
    duplicate = _passage(0.029, [1.0, 0.01])
    distinct = _passage(0.020, [0.0, 1.0])

    assert mmr([best, duplicate, distinct], top_k=2, lambda_=0.7) == [best, distinct]
    assert mmr([best, duplicate, distinct], top_k=2, lambda_=1.0) == [best, duplicate]


def test_queries_follow_the_embedder_that_indexed_the_documents(
    knowledge_base: dict[str, Document], settings: Any
) -> None:
    settings.EMBEDDER = "ollama"  # active embedder changed, nothing re-embedded yet

    embedder = resolve_query_embedder(knowledge_base["refunds"].organization_id)

    assert embedder.name == "hashing-v1"
