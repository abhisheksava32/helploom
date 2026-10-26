"""Text embedders behind one interface.

Two implementations produce 768 dimensional, L2 normalised vectors, so a single
VectorField(dimensions=768) column holds either and cosine similarity is a dot
product:

- OllamaEmbedder ("ollama:nomic-embed-text"): a real neural embedder served by a local
  Ollama, used when it is reachable with the model pulled.
- HashingEmbedder ("hashing-v1"): deterministic feature hashing over words, word
  bigrams and character n-grams. No model, no download, stable across processes and
  machines, so the product (and the test suite) works fully offline.

Each chunk stores the name of the embedder that produced its vector and retrieval
only compares vectors from the active embedder; `manage.py reembed` migrates a corpus
when the active embedder changes.
"""

from __future__ import annotations

import hashlib
import itertools
import logging
import math
import re
from collections import Counter
from collections.abc import Sequence
from functools import lru_cache
from typing import Protocol

import httpx
import numpy as np
from django.conf import settings

from . import ollama

logger = logging.getLogger(__name__)

DIMENSIONS = 768


class EmbeddingError(Exception):
    """The embedder could not produce vectors (for example Ollama went away)."""


class Embedder(Protocol):
    name: str
    dimensions: int
    # Minimum cosine similarity of the best passage before the assistant answers.
    # Similarity scales differ a lot between embedders, so each declares its own
    # default, calibrated with `manage.py run_evals --sweep`.
    default_threshold: float

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...


def embedding_input(document_title: str, heading: str, text: str) -> str:
    """What gets embedded for a chunk: its text plus where it sits.

    The title and heading path disambiguate short passages ("Within 30 days." under
    "Returns > Refund window" means something different from the same words under
    "Warranty"), which helps both embedders.
    """
    context = " > ".join(part for part in (document_title, heading) if part)
    return f"{context}\n\n{text}" if context else text


# Hashing embedder

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)

# Function words carry little meaning on their own. They are down weighted rather than
# dropped so short questions made mostly of them still produce a usable vector.
_STOP_WORD_TEXT = """
    a about above after again against all am an and any are as at be because been before being
    below between both but by can could did do does doing down during each few for from further
    had has have having he her here hers herself him himself his how i if in into is it its itself
    just me more most my myself no nor not now of off on once only or other our ours ourselves out
    over own same she should so some such than that the their theirs them themselves then there
    these they this those through to too under until up very was we were what when where which
    while who whom why will with would you your yours yourself yourselves s t d ll m re ve
    please hi hello thanks thank also may might must shall get got let us
"""
STOP_WORDS = frozenset(_STOP_WORD_TEXT.split())

UNIGRAM_WEIGHT = 1.0
BIGRAM_WEIGHT = 0.7
CHAR_NGRAM_WEIGHT = 0.4
STOP_WORD_FACTOR = 0.15
CHAR_NGRAM_SIZES = (3, 4, 5)


def tokenize(text: str) -> list[str]:
    return _TOKEN.findall(text.lower())


@lru_cache(maxsize=50_000)
def stem(word: str) -> str:
    """A deliberately small English suffix stripper.

    Enough to make "grinder" and "grinders" or "return" and "returned" the same word
    feature; character n-grams already give partial credit for anything subtler.
    """
    if len(word) <= 3 or word.isdigit():
        return word
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("sses"):
        return word[:-2]
    if word.endswith("ing") and len(word) > 5:
        return word[:-3]
    if word.endswith("ed") and len(word) > 4 and not word.endswith("eed"):
        return word[:-2]
    if word.endswith("s") and not word.endswith(("ss", "us", "is")):
        return word[:-1]
    return word


def lexical_features(text: str) -> dict[str, float]:
    """Weighted lexical features shared by the hashing embedder and the extractive
    answerer: stemmed word unigrams and bigrams, plus character 3 to 5 grams with
    boundary markers (so "refund", "refunds" and "refunded" overlap).

    Weights are TF-IDF style without corpus statistics: sublinear term frequency
    (1 + log tf) times a fixed weight per feature type, standing in for IDF. Vectors
    therefore never change as the corpus grows, so adding a document never forces a
    re-embed of the others.
    """
    words = [word if word in STOP_WORDS else stem(word) for word in tokenize(text)]
    counts: Counter[str] = Counter()
    weights: dict[str, float] = {}

    for word in words:
        key = f"w:{word}"
        counts[key] += 1
        weights[key] = UNIGRAM_WEIGHT * (STOP_WORD_FACTOR if word in STOP_WORDS else 1.0)
        if word in STOP_WORDS or len(word) < 3:
            continue
        marked = f"<{word}>"
        for size in CHAR_NGRAM_SIZES:
            for start in range(len(marked) - size + 1):
                gram = f"c:{marked[start : start + size]}"
                counts[gram] += 1
                weights[gram] = CHAR_NGRAM_WEIGHT

    for left, right in itertools.pairwise(words):
        stops = (left in STOP_WORDS) + (right in STOP_WORDS)
        if stops == 2:
            continue
        key = f"b:{left} {right}"
        counts[key] += 1
        weights[key] = BIGRAM_WEIGHT * (0.5 if stops else 1.0)

    return {feature: weights[feature] * (1.0 + math.log(count)) for feature, count in counts.items()}


@lru_cache(maxsize=200_000)
def _bucket(feature: str, dimensions: int) -> tuple[int, float]:
    # BLAKE2b rather than hash(): Python salts str hashes per process, which would make
    # vectors differ between the web process, workers and the test run.
    digest = hashlib.blake2b(feature.encode("utf-8"), digest_size=8).digest()
    value = int.from_bytes(digest, "little")
    # Signed hashing: collisions cancel out on average instead of always adding up.
    return value % dimensions, 1.0 if (value >> 63) & 1 else -1.0


class HashingEmbedder:
    name = "hashing-v1"
    dimensions = DIMENSIONS
    # Calibrated on the eval harness's should refuse cases (run_evals --sweep).
    default_threshold = 0.15

    def _vector(self, text: str) -> list[float]:
        vector = np.zeros(self.dimensions, dtype=np.float64)
        for feature, weight in lexical_features(text).items():
            index, sign = _bucket(feature, self.dimensions)
            vector[index] += sign * weight
        norm = float(np.linalg.norm(vector))
        if norm == 0.0:
            return vector.tolist()
        return (vector / norm).tolist()

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [self._vector(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._vector(text)


# Ollama embedder


class OllamaEmbedder:
    # nomic-embed-text is trained with task prefixes; using them noticeably improves
    # retrieval compared with raw text.
    DOCUMENT_PREFIX = "search_document: "
    QUERY_PREFIX = "search_query: "
    dimensions = DIMENSIONS
    default_threshold = 0.50

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model = model or settings.OLLAMA_EMBED_MODEL
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")
        self.name = f"ollama:{self.model}"
        self._transport = transport  # tests inject httpx.MockTransport

    def _post(self, client: httpx.Client, inputs: list[str]) -> list[list[float]]:
        response = client.post("/api/embed", json={"model": self.model, "input": inputs})
        if response.status_code == 404:
            # Ollama before 0.3 only has the one at a time endpoint.
            return [self._legacy(client, text) for text in inputs]
        response.raise_for_status()
        vectors = response.json().get("embeddings")
        if not isinstance(vectors, list) or len(vectors) != len(inputs):
            raise EmbeddingError("Ollama returned an unexpected embeddings payload.")
        return vectors

    def _legacy(self, client: httpx.Client, text: str) -> list[float]:
        response = client.post("/api/embeddings", json={"model": self.model, "prompt": text})
        response.raise_for_status()
        vector = response.json().get("embedding")
        if not isinstance(vector, list):
            raise EmbeddingError("Ollama returned an unexpected embedding payload.")
        return vector

    def _embed(self, inputs: list[str]) -> list[list[float]]:
        if not inputs:
            return []
        timeout = httpx.Timeout(
            settings.OLLAMA_TIMEOUT_SECONDS, connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS
        )
        try:
            with httpx.Client(base_url=self.base_url, timeout=timeout, transport=self._transport) as client:
                vectors = self._post(client, inputs)
        except httpx.HTTPError as exc:
            raise EmbeddingError(f"Ollama embeddings failed: {exc.__class__.__name__}") from exc
        result: list[list[float]] = []
        for vector in vectors:
            if len(vector) != self.dimensions:
                raise EmbeddingError(
                    f"{self.model} returned {len(vector)} dimensions; the index stores {self.dimensions}."
                )
            array = np.asarray(vector, dtype=np.float64)
            norm = float(np.linalg.norm(array))
            result.append((array / norm).tolist() if norm else array.tolist())
        return result

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return self._embed([self.DOCUMENT_PREFIX + text for text in texts])

    def embed_query(self, text: str) -> list[float]:
        return self._embed([self.QUERY_PREFIX + text])[0]


# Selection


def get_embedder() -> Embedder:
    """The active embedder for new chunks and for queries.

    EMBEDDER=hashing and EMBEDDER=ollama are explicit. auto prefers Ollama when the
    probe (cached for PROVIDER_PROBE_TTL_SECONDS) says it is up with the model pulled.
    """
    choice = settings.EMBEDDER
    if choice == "hashing":
        return HashingEmbedder()
    if choice == "ollama":
        return OllamaEmbedder()
    status = ollama.probe()
    if status.has_model(settings.OLLAMA_EMBED_MODEL):
        return OllamaEmbedder()
    return HashingEmbedder()


def embedder_by_name(name: str) -> Embedder | None:
    if name == HashingEmbedder.name:
        return HashingEmbedder()
    if name.startswith("ollama:"):
        return OllamaEmbedder(model=name.removeprefix("ollama:"))
    return None


def embed_in_batches(
    embedder: Embedder, texts: Sequence[str], batch_size: int | None = None
) -> list[list[float]]:
    size = max(1, batch_size or settings.EMBEDDING_BATCH_SIZE)
    vectors: list[list[float]] = []
    for start in range(0, len(texts), size):
        vectors.extend(embedder.embed_documents(texts[start : start + size]))
    return vectors
