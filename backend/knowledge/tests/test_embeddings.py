"""Embedders: deterministic hashing vectors, the Ollama client and selection."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import pytest

from knowledge import ollama
from knowledge.embeddings import (
    DIMENSIONS,
    EmbeddingError,
    HashingEmbedder,
    OllamaEmbedder,
    embed_in_batches,
    embedding_input,
    get_embedder,
    lexical_features,
    stem,
)

BACKEND_DIR = Path(__file__).resolve().parents[2]


def _cosine(a: list[float], b: list[float]) -> float:
    return float(np.dot(a, b))


def test_hashing_vectors_are_normalised_and_768_wide() -> None:
    vector = HashingEmbedder().embed_query("How long do refunds take?")

    assert len(vector) == DIMENSIONS
    assert np.linalg.norm(vector) == pytest.approx(1.0)


def test_hashing_is_deterministic_across_instances() -> None:
    text = "Refunds are issued within 5 business days."

    assert HashingEmbedder().embed_query(text) == HashingEmbedder().embed_documents([text])[0]


def test_hashing_is_identical_across_processes_with_different_hash_seeds() -> None:
    """Python salts str hashes per process; the embedder must not depend on it."""
    script = (
        "import json, django, os; os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'helploom.settings'); "
        "django.setup(); from knowledge.embeddings import HashingEmbedder; "
        "print(json.dumps(HashingEmbedder().embed_query('Refund window for grinders')[:16]))"
    )
    outputs = []
    for seed in ("1", "2"):
        env = {**os.environ, "PYTHONHASHSEED": seed, "TESTING": "true"}
        result = subprocess.run(
            [sys.executable, "-c", script],
            cwd=BACKEND_DIR,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(json.loads(result.stdout.strip().splitlines()[-1]))

    assert outputs[0] == outputs[1]
    assert outputs[0][:16] == pytest.approx(HashingEmbedder().embed_query("Refund window for grinders")[:16])


def test_related_texts_are_closer_than_unrelated_ones() -> None:
    embedder = HashingEmbedder()
    question = embedder.embed_query("How long do refunds take?")
    related = embedder.embed_query("Refunds are issued within 5 business days.")
    unrelated = embedder.embed_query("Our office cat is called Biscuit.")

    assert _cosine(question, related) > _cosine(question, unrelated) + 0.1


def test_word_forms_share_features() -> None:
    assert stem("grinders") == stem("grinder") == "grinder"
    assert stem("returned") == "return"
    assert stem("policies") == "policy"
    assert stem("bus") == "bus"
    assert "w:refund" in lexical_features("Refunds")


def test_empty_text_embeds_to_a_zero_vector() -> None:
    assert not any(HashingEmbedder().embed_query("  "))


def test_embedding_input_adds_title_and_heading_context() -> None:
    assert embedding_input("Refund policy", "Returns > Window", "Within 30 days.") == (
        "Refund policy > Returns > Window\n\nWithin 30 days."
    )
    assert embedding_input("", "", "Body") == "Body"


def test_embed_in_batches_splits_requests() -> None:
    calls: list[int] = []

    class Recorder(HashingEmbedder):
        def embed_documents(self, texts: Any) -> list[list[float]]:
            calls.append(len(texts))
            return super().embed_documents(texts)

    vectors = embed_in_batches(Recorder(), [f"text {i}" for i in range(7)], batch_size=3)

    assert calls == [3, 3, 1]
    assert len(vectors) == 7


def _ollama_embedder(handler: Any) -> OllamaEmbedder:
    return OllamaEmbedder(
        model="nomic-embed-text", base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )


def test_ollama_embedder_uses_task_prefixes_and_normalises() -> None:
    seen: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        payload = json.loads(request.content)
        seen.append(payload)
        return httpx.Response(200, json={"embeddings": [[3.0, 4.0] + [0.0] * 766 for _ in payload["input"]]})

    embedder = _ollama_embedder(handler)
    documents = embedder.embed_documents(["Refunds take 5 days."])
    query = embedder.embed_query("refund time")

    assert seen[0] == {"model": "nomic-embed-text", "input": ["search_document: Refunds take 5 days."]}
    assert seen[1]["input"] == ["search_query: refund time"]
    assert documents[0][:2] == pytest.approx([0.6, 0.8])
    assert embedder.name == "ollama:nomic-embed-text"
    assert len(query) == DIMENSIONS


def test_ollama_embedder_rejects_the_wrong_dimension() -> None:
    embedder = _ollama_embedder(lambda request: httpx.Response(200, json={"embeddings": [[1.0, 2.0]]}))

    with pytest.raises(EmbeddingError, match="768"):
        embedder.embed_query("x")


def test_ollama_embedder_falls_back_to_the_legacy_endpoint() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/embed":
            return httpx.Response(404)
        return httpx.Response(200, json={"embedding": [1.0] + [0.0] * 767})

    assert _ollama_embedder(handler).embed_query("x")[0] == pytest.approx(1.0)


def test_ollama_connection_errors_become_embedding_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(EmbeddingError):
        _ollama_embedder(handler).embed_documents(["x"])


def test_auto_picks_ollama_only_when_the_model_is_pulled(settings: Any) -> None:
    settings.EMBEDDER = "auto"
    settings.OLLAMA_EMBED_MODEL = "nomic-embed-text"

    assert get_embedder().name == "hashing-v1"

    ollama.set_probe_result(ollama.OllamaStatus(reachable=True, models=frozenset({"llama3.2:latest"})))
    assert get_embedder().name == "hashing-v1"

    ollama.set_probe_result(
        ollama.OllamaStatus(reachable=True, models=frozenset({"nomic-embed-text:latest"}))
    )
    assert get_embedder().name == "ollama:nomic-embed-text"


def test_explicit_embedder_settings_win(settings: Any) -> None:
    settings.EMBEDDER = "hashing"
    ollama.set_probe_result(
        ollama.OllamaStatus(reachable=True, models=frozenset({"nomic-embed-text:latest"}))
    )

    assert get_embedder().name == "hashing-v1"
