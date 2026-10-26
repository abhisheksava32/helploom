"""Answers from the Claude API through the official anthropic SDK (never raw HTTP).

The request shape is fixed by docs/DESIGN.md, "Provider abstraction":

- The stable system prompt is sent as a text block with cache_control, so repeated
  questions to the same organisation read it from the prompt cache.
- output_config effort "low" keeps time to first token down on the chat route.
- The server side fallback beta re-runs a refused request on CLAUDE_FALLBACK_MODEL
  inside the same call, so final.model is recorded as the model that actually served
  the answer.
- No thinking, temperature, top_p or top_k parameters (Claude Opus 5.5 rejects
  disabling thinking and sampling parameters) and no assistant prefill.

The API key is read by the SDK from ANTHROPIC_API_KEY and never touches this code.
"""

from __future__ import annotations

import asyncio
import logging
import weakref
from collections.abc import AsyncGenerator
from typing import Any

import anthropic
from django.conf import settings

from ..prompts import Prompt
from .base import Completed, ProviderError, ProviderEvent, StopReason, TextDelta, Usage

logger = logging.getLogger(__name__)

# One client per event loop: the SDK's HTTP connection pool is bound to the loop that
# opened it, and reusing it across questions saves a TLS handshake per answer.
_clients: weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, anthropic.AsyncAnthropic] = (
    weakref.WeakKeyDictionary()
)


def shared_client() -> anthropic.AsyncAnthropic:
    loop = asyncio.get_running_loop()
    client = _clients.get(loop)
    if client is None:
        client = anthropic.AsyncAnthropic()  # reads ANTHROPIC_API_KEY from env; never hardcode keys
        _clients[loop] = client
    return client


def claude_configured() -> bool:
    return bool(settings.ANTHROPIC_API_KEY)


def _stop_reason(final: Any) -> str:
    if final.stop_reason == "refusal":
        return StopReason.REFUSAL
    if final.stop_reason == "max_tokens":
        return StopReason.MAX_TOKENS
    return StopReason.END_TURN


def _usage(final: Any) -> Usage:
    usage = final.usage
    return Usage(
        input_tokens=int(usage.input_tokens or 0),
        output_tokens=int(usage.output_tokens or 0),
        cache_read_input_tokens=int(getattr(usage, "cache_read_input_tokens", 0) or 0),
        cache_creation_input_tokens=int(getattr(usage, "cache_creation_input_tokens", 0) or 0),
    )


def _final_text(final: Any) -> str:
    # After a mid-stream fallback the content holds the declined partial, a fallback
    # marker block and the fallback model's continuation; the text blocks together
    # are the answer the customer saw.
    return "".join(block.text for block in final.content if getattr(block, "type", None) == "text")


class ClaudeProvider:
    name = "claude"

    def __init__(self, client: anthropic.AsyncAnthropic | None = None, model: str | None = None) -> None:
        self._client = client
        self.model = model or settings.CLAUDE_MODEL

    async def is_available(self) -> bool:
        return claude_configured()

    async def stream(self, prompt: Prompt) -> AsyncGenerator[ProviderEvent]:
        client = self._client or shared_client()
        model = self.model  # default "claude-opus-5-5"; exactly this id string, no date suffix
        messages: Any = [{"role": message.role, "content": message.content} for message in prompt.messages]
        effort: Any = settings.CLAUDE_EFFORT
        try:
            async with client.beta.messages.stream(
                model=model,
                max_tokens=settings.CLAUDE_MAX_TOKENS,
                system=[{"type": "text", "text": prompt.system, "cache_control": {"type": "ephemeral"}}],
                messages=messages,
                output_config={"effort": effort},  # chat route: low effort keeps latency down
                betas=[settings.CLAUDE_FALLBACK_BETA],
                fallbacks=[{"model": settings.CLAUDE_FALLBACK_MODEL}],  # server-side refusal fallback
                timeout=settings.CLAUDE_TIMEOUT_SECONDS,
            ) as stream:
                async for text in stream.text_stream:
                    yield TextDelta(text)
                final = await stream.get_final_message()
        except anthropic.AuthenticationError as exc:
            logger.warning("Claude rejected the API key; falling back to the extractive provider")
            raise ProviderError("Claude authentication failed.") from exc
        except anthropic.RateLimitError as exc:
            logger.warning("Claude rate limit reached; falling back to the extractive provider")
            raise ProviderError("Claude rate limited the request.") from exc
        except anthropic.APIStatusError as exc:
            logger.warning(
                "Claude returned HTTP %s; falling back to the extractive provider", exc.status_code
            )
            raise ProviderError(f"Claude returned HTTP {exc.status_code}.") from exc
        except anthropic.APIConnectionError as exc:
            logger.warning("Could not reach the Claude API (%s); falling back", exc.__class__.__name__)
            raise ProviderError("Claude is unreachable.") from exc

        # Check the stop reason before trusting the content: a refusal's partial text
        # must not be shown as an answer.
        stop_reason = _stop_reason(final)
        if stop_reason == StopReason.REFUSAL:
            details = getattr(final, "stop_details", None)
            logger.info("Claude declined to answer (category %s)", getattr(details, "category", None))
        yield Completed(
            stop_reason=stop_reason,
            model=str(final.model or model),
            usage=_usage(final),
            text=None if stop_reason == StopReason.REFUSAL else _final_text(final),
        )
