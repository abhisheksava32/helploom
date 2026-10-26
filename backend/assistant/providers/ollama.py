"""Answers from a local Ollama server, streamed over its NDJSON chat API.

POST /api/chat with stream: true returns one JSON object per line: message.content
deltas until a final object with done: true, which also carries token counts
(prompt_eval_count, eval_count). Local inference costs nothing, so usage is recorded
for latency and volume reports only.
"""

from __future__ import annotations

import json
import logging
from collections.abc import AsyncGenerator
from typing import Any

import httpx
from django.conf import settings

from knowledge import ollama as ollama_probe

from ..prompts import Prompt
from .base import Completed, ProviderError, ProviderEvent, StopReason, TextDelta, Usage

logger = logging.getLogger(__name__)


class OllamaProvider:
    name = "ollama"

    def __init__(
        self,
        model: str | None = None,
        base_url: str | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.model = model or settings.OLLAMA_MODEL
        self.base_url = (base_url or settings.OLLAMA_URL).rstrip("/")
        self._transport = transport  # tests inject httpx.MockTransport

    async def is_available(self) -> bool:
        status = await ollama_probe.aprobe()
        return status.has_model(self.model)

    def _payload(self, prompt: Prompt) -> dict[str, Any]:
        return {
            "model": self.model,
            "messages": [
                {"role": "system", "content": prompt.system},
                *({"role": message.role, "content": message.content} for message in prompt.messages),
            ],
            "stream": True,
            "keep_alive": settings.OLLAMA_KEEP_ALIVE,
            # Grounded support answers want the most likely wording, not creativity.
            "options": {"temperature": 0.2},
        }

    async def stream(self, prompt: Prompt) -> AsyncGenerator[ProviderEvent]:
        timeout = httpx.Timeout(
            settings.OLLAMA_TIMEOUT_SECONDS, connect=settings.OLLAMA_CONNECT_TIMEOUT_SECONDS
        )
        try:
            async with (
                httpx.AsyncClient(
                    base_url=self.base_url, timeout=timeout, transport=self._transport
                ) as client,
                client.stream("POST", "/api/chat", json=self._payload(prompt)) as response,
            ):
                if response.status_code >= 400:
                    await response.aread()
                    raise ProviderError(f"Ollama returned HTTP {response.status_code}: {response.text[:200]}")
                async for line in response.aiter_lines():
                    if not line.strip():
                        continue
                    data = json.loads(line)
                    if data.get("error"):
                        raise ProviderError(f"Ollama error: {str(data['error'])[:200]}")
                    content = (data.get("message") or {}).get("content") or ""
                    if content:
                        yield TextDelta(content)
                    if data.get("done"):
                        yield Completed(
                            stop_reason=(
                                StopReason.MAX_TOKENS
                                if data.get("done_reason") == "length"
                                else StopReason.END_TURN
                            ),
                            model=str(data.get("model") or self.model),
                            usage=Usage(
                                input_tokens=int(data.get("prompt_eval_count") or 0),
                                output_tokens=int(data.get("eval_count") or 0),
                            ),
                        )
                        return
        except httpx.HTTPError as exc:
            raise ProviderError(f"Ollama request failed: {exc.__class__.__name__}") from exc
        except (json.JSONDecodeError, ValueError, TypeError) as exc:
            raise ProviderError("Ollama sent a malformed stream.") from exc
        raise ProviderError("Ollama closed the stream before finishing the answer.")
