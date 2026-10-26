"""The interface every answer provider implements.

A provider turns a Prompt into a stream of TextDelta events followed by exactly one
Completed event. Providers raise ProviderError for any failure the pipeline should
recover from; the pipeline then answers with the extractive provider, so a dead
Ollama or a revoked API key degrades answers instead of breaking them.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from dataclasses import asdict, dataclass, field
from typing import Protocol

from ..prompts import Prompt


class StopReason:
    END_TURN = "end_turn"
    MAX_TOKENS = "max_tokens"
    REFUSAL = "refusal"
    CANCELLED = "cancelled"


@dataclass(frozen=True)
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_input_tokens: int = 0
    cache_creation_input_tokens: int = 0

    def as_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class TextDelta:
    text: str


@dataclass(frozen=True)
class Completed:
    stop_reason: str
    model: str  # the model that actually served the answer (a fallback included)
    usage: Usage = field(default_factory=Usage)
    # The provider's own record of the full answer, when it has one. It wins over the
    # concatenated deltas, for example after a server side fallback.
    text: str | None = None


ProviderEvent = TextDelta | Completed


class ProviderError(Exception):
    """The provider failed; the pipeline answers with the extractive provider."""


class ChatProvider(Protocol):
    name: str
    model: str

    async def is_available(self) -> bool: ...

    def stream(self, prompt: Prompt) -> AsyncGenerator[ProviderEvent]: ...
