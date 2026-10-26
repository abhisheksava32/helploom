"""Reachability probe for a local Ollama server, shared by embeddings and answer providers.

Both the embedder choice (EMBEDDER=auto) and the answer provider choice
(LLM_PROVIDER=auto) depend on whether Ollama is up and has the right model pulled.
Probing on every question would add a network round trip to each answer, so the
result of GET /api/tags is cached in process for PROVIDER_PROBE_TTL_SECONDS. A missing
Ollama therefore costs one quick connect timeout per TTL, not one per question.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
from django.conf import settings

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OllamaStatus:
    reachable: bool
    models: frozenset[str] = field(default_factory=frozenset)
    detail: str = ""

    def has_model(self, name: str) -> bool:
        """Ollama lists models as "name:tag"; a configured name without a tag means latest."""
        if not self.reachable:
            return False
        wanted = name if ":" in name else f"{name}:latest"
        return wanted in self.models or name in self.models


_lock = threading.Lock()
_cached: tuple[float, OllamaStatus] | None = None


def _timeout() -> httpx.Timeout:
    return httpx.Timeout(
        settings.OLLAMA_CONNECT_TIMEOUT_SECONDS * 2, connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS
    )


def _parse(payload: Any) -> OllamaStatus:
    names: set[str] = set()
    entries = payload.get("models", []) if isinstance(payload, dict) else []
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        name = entry.get("name") or entry.get("model")
        if isinstance(name, str):
            names.add(name)
    return OllamaStatus(
        reachable=True, models=frozenset(names), detail=f"Reachable at {settings.OLLAMA_URL}."
    )


def _unreachable(exc: Exception) -> OllamaStatus:
    logger.info("Ollama is not reachable at %s: %s", settings.OLLAMA_URL, exc.__class__.__name__)
    return OllamaStatus(reachable=False, detail=f"Not reachable at {settings.OLLAMA_URL}.")


def _get_cached() -> OllamaStatus | None:
    with _lock:
        if _cached is not None and _cached[0] > time.monotonic():
            return _cached[1]
    return None


def _store(status: OllamaStatus) -> OllamaStatus:
    global _cached
    with _lock:
        _cached = (time.monotonic() + settings.PROVIDER_PROBE_TTL_SECONDS, status)
    return status


def probe() -> OllamaStatus:
    """Synchronous probe for ingestion threads, management commands and REST views."""
    cached = _get_cached()
    if cached is not None:
        return cached
    try:
        response = httpx.get(f"{settings.OLLAMA_URL}/api/tags", timeout=_timeout())
        response.raise_for_status()
        status = _parse(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        status = _unreachable(exc)
    return _store(status)


async def aprobe() -> OllamaStatus:
    """Async probe for the answer pipeline, so a slow Ollama never blocks the event loop."""
    cached = _get_cached()
    if cached is not None:
        return cached
    try:
        async with httpx.AsyncClient(timeout=_timeout()) as client:
            response = await client.get(f"{settings.OLLAMA_URL}/api/tags")
            response.raise_for_status()
            status = _parse(response.json())
    except (httpx.HTTPError, ValueError) as exc:
        status = _unreachable(exc)
    return _store(status)


def reset_probe_cache() -> None:
    global _cached
    with _lock:
        _cached = None


def set_probe_result(status: OllamaStatus) -> None:
    """Seed the cache, for tests and for callers that just learned Ollama went away."""
    _store(status)
