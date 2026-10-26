"""Hybrid retrieval over knowledge.Chunk: pgvector cosine search plus PostgreSQL
full-text search, fused with reciprocal rank fusion and diversified with maximal
marginal relevance. See docs/DESIGN.md, "Retrieval design".

Tenant isolation lives here, in the query layer: both sides filter
organization_id = <tenant> in SQL (Chunk carries a copied organization_id, so no join
is needed), and nothing in this module accepts a chunk id from outside.
"""

from __future__ import annotations

import logging
import math
import time
from collections import Counter
from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

import numpy as np
from django.conf import settings
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.db import connection, transaction
from django.db.models import Count, F
from pgvector.django import CosineDistance

from knowledge.embeddings import Embedder, EmbeddingError, embedder_by_name, get_embedder, tokenize
from knowledge.models import SEARCH_CONFIG, Chunk, Document, DocumentStatus

logger = logging.getLogger(__name__)

Mode = Literal["hybrid", "vector", "keyword"]
MAX_KEYWORD_TERMS = 32
_FIELDS = (
    "id",
    "document_id",
    "document__title",
    "ordinal",
    "location",
    "heading",
    "text",
    "page_number",
    "embedding",
)


def _tie_break(row: dict) -> tuple[str, int]:
    # Content based, so equal scores always come out in the same order (random UUIDs
    # would make the evals flaky).
    return row["document__title"], row["ordinal"]


@dataclass
class Passage:
    chunk_id: UUID
    document_id: UUID
    document_title: str
    location: str
    heading: str
    text: str
    page_number: int | None = None
    score: float = 0.0  # fused reciprocal rank fusion score, higher is better
    similarity: float | None = None  # cosine similarity; None for keyword only matches
    vector_rank: int | None = None
    keyword_rank: int | None = None
    embedding: np.ndarray | None = field(default=None, repr=False)


@dataclass
class RetrievalResult:
    query: str
    embedder: str
    threshold: float
    mode: Mode
    passages: list[Passage]
    top_similarity: float | None
    keyword_hits: int
    elapsed_ms: int = 0

    @property
    def would_answer(self) -> bool:
        """The relevance gate: only vector similarity counts, because a single shared
        common word on the keyword side is too weak a signal to justify an answer."""
        return self.top_similarity is not None and self.top_similarity >= self.threshold


def relevance_threshold(embedder: Embedder) -> float:
    override = settings.RELEVANCE_THRESHOLD
    return float(override) if override is not None else embedder.default_threshold


def keyword_terms(query: str) -> str:
    """websearch_to_tsquery input that matches any of the question's words.

    Questions are long and natural; requiring every word (the default AND) would miss
    most passages. ts_rank_cd then rewards passages containing more of the words close
    together. Only word characters survive, so quotes, a leading "-" or a stray "or"
    in the question cannot change the query's meaning.
    """
    words: list[str] = []
    for word in tokenize(query):
        if word not in ("or", "and") and word not in words:
            words.append(word)
    return " or ".join(words[:MAX_KEYWORD_TERMS])


def resolve_query_embedder(organization_id: UUID | str) -> Embedder:
    """The embedder whose vectors this organisation's queries are compared with.

    Normally the active embedder. If the organisation has no documents indexed by it
    yet (the active embedder just changed, for example Ollama came up in auto mode),
    search the embedder that indexed most of its documents instead, so answers keep
    working until `manage.py reembed` catches up.
    """
    active = get_embedder()
    counts = Counter(
        {
            row["embedder"]: row["n"]
            for row in Document.objects.for_organization(organization_id)
            .filter(status=DocumentStatus.READY)
            .exclude(embedder="")
            .values("embedder")
            .annotate(n=Count("id"))
        }
    )
    if not counts or active.name in counts:
        return active
    fallback = embedder_by_name(counts.most_common(1)[0][0])
    if fallback is None:
        return active
    logger.info(
        "Organization %s has no %s chunks yet; searching %s", organization_id, active.name, fallback.name
    )
    return fallback


def _passage(row: dict) -> Passage:
    return Passage(
        chunk_id=row["id"],
        document_id=row["document_id"],
        document_title=row["document__title"],
        location=row["location"],
        heading=row["heading"],
        text=row["text"],
        page_number=row["page_number"],
        embedding=row["embedding"],
    )


def _vector_side(
    organization_id: UUID | str, embedder_name: str, vector: list[float], limit: int
) -> list[dict]:
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute(f"SET LOCAL hnsw.ef_search = {int(settings.HNSW_EF_SEARCH)}")
            # pgvector 0.8: keep scanning the HNSW graph when the tenant filter
            # discards candidates, so a small tenant in a large table still gets
            # `limit` rows back.
            cursor.execute("SET LOCAL hnsw.iterative_scan = relaxed_order")
        rows = list(
            Chunk.objects.for_organization(organization_id)
            .filter(embedder=embedder_name, embedding__isnull=False)
            .annotate(distance=CosineDistance("embedding", vector))
            .order_by("distance")
            .values(*_FIELDS, "distance")[:limit]
        )
    # relaxed_order may return rows slightly out of order; restore exact order. The
    # SQL itself must order by distance alone, or PostgreSQL cannot use the index.
    rows.sort(key=lambda row: (row["distance"], *_tie_break(row)))
    return rows


def _keyword_side(organization_id: UUID | str, embedder_name: str, query: str, limit: int) -> list[dict]:
    terms = keyword_terms(query)
    if not terms:
        return []
    search_query = SearchQuery(terms, search_type="websearch", config=SEARCH_CONFIG)
    return list(
        Chunk.objects.for_organization(organization_id)
        .filter(embedder=embedder_name, search_vector=search_query)
        .annotate(rank=SearchRank(F("search_vector"), search_query, cover_density=True))
        .order_by("-rank", "document__title", "ordinal")
        .values(*_FIELDS, "rank")[:limit]
    )


def fuse(vector_rows: list[dict], keyword_rows: list[dict], k: int | None = None) -> list[Passage]:
    """Reciprocal rank fusion: score(d) = sum over sides of 1 / (k + rank).

    Cosine similarity and ts_rank_cd live on unrelated scales (ts_rank_cd is not even
    comparable between queries), so only ranks are combined. Passages both sides agree
    on rise to the top without any per corpus weight tuning.
    """
    k = settings.RRF_K if k is None else k
    passages: dict[UUID, Passage] = {}
    for rank, row in enumerate(vector_rows, start=1):
        passage = passages.setdefault(row["id"], _passage(row))
        passage.vector_rank = rank
        passage.similarity = max(0.0, 1.0 - float(row["distance"]))
        passage.score += 1.0 / (k + rank)
    for rank, row in enumerate(keyword_rows, start=1):
        passage = passages.setdefault(row["id"], _passage(row))
        passage.keyword_rank = rank
        passage.score += 1.0 / (k + rank)
    return sorted(
        passages.values(),
        key=lambda p: (-p.score, p.vector_rank or math.inf, p.keyword_rank or math.inf),
    )


def mmr(candidates: list[Passage], top_k: int, lambda_: float | None = None) -> list[Passage]:
    """Maximal marginal relevance: trade a little relevance for coverage.

    Support documents repeat themselves (the refund window is in the FAQ, the policy
    and the terms). Greedy selection of lambda * relevance - (1 - lambda) * max
    similarity to what is already picked gives the model more distinct facts in the
    same prompt budget. Runs in numpy over a few dozen candidates.
    """
    lambda_ = settings.RETRIEVAL_MMR_LAMBDA if lambda_ is None else lambda_
    if len(candidates) <= 1 or top_k <= 1 or any(p.embedding is None for p in candidates):
        return candidates[:top_k]
    scores = np.array([p.score for p in candidates], dtype=np.float64)
    # Scale by the best score rather than min-max: min-max would give the weakest
    # candidate zero relevance however close it is, exaggerating small RRF gaps.
    relevance = scores / scores.max() if scores.max() > 0 else np.ones_like(scores)
    vectors = np.stack([np.asarray(p.embedding, dtype=np.float64) for p in candidates])
    similarity = vectors @ vectors.T

    selected = [int(np.argmax(relevance))]
    remaining = [i for i in range(len(candidates)) if i != selected[0]]
    while remaining and len(selected) < top_k:
        redundancy = similarity[np.ix_(remaining, selected)].max(axis=1)
        marginal = lambda_ * relevance[remaining] - (1.0 - lambda_) * redundancy
        best = remaining[int(np.argmax(marginal))]
        selected.append(best)
        remaining.remove(best)
    return [candidates[i] for i in selected]


def search(
    organization_id: UUID | str,
    query: str,
    *,
    top_k: int | None = None,
    mode: Mode = "hybrid",
    use_mmr: bool | None = None,
    embedder: Embedder | None = None,
) -> RetrievalResult:
    """Retrieve the top passages for a question inside one organisation."""
    started = time.monotonic()
    top_k = top_k or settings.RETRIEVAL_TOP_K
    candidates = max(settings.RETRIEVAL_CANDIDATES, top_k)
    use_mmr = settings.RETRIEVAL_MMR if use_mmr is None else use_mmr
    embedder = embedder or resolve_query_embedder(organization_id)

    vector_rows: list[dict] = []
    if mode in ("hybrid", "vector"):
        try:
            vector = embedder.embed_query(query)
        except EmbeddingError:
            # Keyword search still works; the relevance gate will then decline to
            # answer, which is the honest outcome when we cannot judge similarity.
            logger.warning(
                "Query embedding failed with %s; using keyword search only", embedder.name, exc_info=True
            )
        else:
            vector_rows = _vector_side(organization_id, embedder.name, vector, candidates)
    keyword_rows = (
        _keyword_side(organization_id, embedder.name, query, candidates)
        if mode in ("hybrid", "keyword")
        else []
    )

    fused = fuse(vector_rows, keyword_rows)
    passages = mmr(fused, top_k) if use_mmr else fused[:top_k]
    similarities = [max(0.0, 1.0 - float(row["distance"])) for row in vector_rows]
    return RetrievalResult(
        query=query,
        embedder=embedder.name,
        threshold=relevance_threshold(embedder),
        mode=mode,
        passages=passages,
        top_similarity=max(similarities) if similarities else None,
        keyword_hits=len(keyword_rows),
        elapsed_ms=int((time.monotonic() - started) * 1000),
    )
