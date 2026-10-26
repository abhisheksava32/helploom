"""Answer providers behind one interface, and the rule that picks one.

| LLM_PROVIDER | Behaviour                                                              |
| ------------ | ---------------------------------------------------------------------- |
| auto         | Ollama when reachable with OLLAMA_MODEL pulled, else extractive        |
| ollama       | Ollama; extractive with a logged warning when it is unreachable        |
| claude       | Claude when ANTHROPIC_API_KEY is set; otherwise extractive (warning)   |
| extractive   | Always extractive                                                      |

Reachability comes from knowledge.ollama's cached probe, so choosing a provider costs
no network round trip on most questions.
"""

from __future__ import annotations

import logging

from django.conf import settings

from knowledge import ollama as ollama_probe

from .base import ChatProvider, Completed, ProviderError, ProviderEvent, StopReason, TextDelta, Usage
from .claude import ClaudeProvider, claude_configured
from .extractive import ExtractiveProvider
from .ollama import OllamaProvider

logger = logging.getLogger(__name__)


def choose_provider(ollama_status: ollama_probe.OllamaStatus) -> ChatProvider:
    configured = settings.LLM_PROVIDER
    if configured == "extractive":
        return ExtractiveProvider()
    if configured == "claude":
        if claude_configured():
            return ClaudeProvider()
        logger.warning("LLM_PROVIDER=claude but ANTHROPIC_API_KEY is not set; answering extractively")
        return ExtractiveProvider()
    if ollama_status.has_model(settings.OLLAMA_MODEL):
        return OllamaProvider()
    if configured == "ollama":
        logger.warning("Ollama is not available with %s; answering extractively", settings.OLLAMA_MODEL)
    return ExtractiveProvider()


def _needs_probe() -> bool:
    return settings.LLM_PROVIDER in ("auto", "ollama")


async def resolve_provider() -> ChatProvider:
    """The provider for the next answer (async: used by the answer pipeline)."""
    status = await ollama_probe.aprobe() if _needs_probe() else ollama_probe.OllamaStatus(reachable=False)
    return choose_provider(status)


def active_provider() -> ChatProvider:
    """The same decision from synchronous code, for the provider status endpoint."""
    status = ollama_probe.probe() if _needs_probe() else ollama_probe.OllamaStatus(reachable=False)
    return choose_provider(status)


__all__ = [
    "ChatProvider",
    "ClaudeProvider",
    "Completed",
    "ExtractiveProvider",
    "OllamaProvider",
    "ProviderError",
    "ProviderEvent",
    "StopReason",
    "TextDelta",
    "Usage",
    "active_provider",
    "choose_provider",
    "claude_configured",
    "resolve_provider",
]
