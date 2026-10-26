"""Answer providers: extractive, Ollama over NDJSON, Claude through the SDK, and the
selection rule. No test touches the network."""

from __future__ import annotations

import json
import uuid
from types import SimpleNamespace
from typing import Any

import anthropic
import httpx
import httpx2
import pytest

from assistant import providers
from assistant.prompts import NOT_FOUND_SENTENCE, Prompt, PromptMessage, build_prompt
from assistant.providers import (
    ClaudeProvider,
    Completed,
    ExtractiveProvider,
    OllamaProvider,
    ProviderError,
    StopReason,
    TextDelta,
    choose_provider,
)
from assistant.providers.extractive import compose_answer
from assistant.retrieval import Passage
from knowledge import ollama


def passage(text: str, title: str = "Refund policy") -> Passage:
    return Passage(uuid.uuid4(), uuid.uuid4(), title, "Returns", "", text, similarity=0.6)


def prompt(question: str = "How long do refunds take?", passages: list[Passage] | None = None) -> Prompt:
    return build_prompt(
        business_name="Kettlewick Coffee Co.",
        tone="friendly",
        question=question,
        passages=passages or [passage("Refunds are issued within 5 business days. We love coffee.")],
        history=[PromptMessage("user", "Hi"), PromptMessage("assistant", "Hello!")],
    )


async def collect(provider: Any, request: Prompt) -> list[Any]:
    return [event async for event in provider.stream(request)]


# Extractive


def test_extractive_answers_cite_the_sentences_they_use() -> None:
    sources = [
        passage("Our roastery is in Asheville. Refunds are issued within 5 business days."),
        passage("Exchanges are free for unused items.", title="Exchanges"),
    ]

    answer = compose_answer("How long do refunds take?", sources)

    assert answer == "Refunds are issued within 5 business days [1]."


def test_extractive_says_not_found_when_nothing_overlaps() -> None:
    assert compose_answer("Who won the world cup?", [passage("Refunds take 5 days.")]) == NOT_FOUND_SENTENCE


async def test_extractive_streams_sentences_then_completes() -> None:
    events = await collect(ExtractiveProvider(), prompt())

    deltas = [e.text for e in events if isinstance(e, TextDelta)]
    completed = events[-1]
    assert isinstance(completed, Completed)
    assert "".join(deltas) == completed.text
    assert completed.model == "extractive-v1"
    assert completed.usage.input_tokens == 0


# Ollama


def ollama_provider(handler: Any) -> OllamaProvider:
    return OllamaProvider(
        model="llama3.2", base_url="http://ollama.test", transport=httpx.MockTransport(handler)
    )


async def test_ollama_streams_ndjson_and_reports_usage(settings: Any) -> None:
    settings.OLLAMA_KEEP_ALIVE = "5m"
    seen: dict[str, Any] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(json.loads(request.content))
        lines = [
            {"message": {"role": "assistant", "content": "Refunds take "}, "done": False},
            {"message": {"role": "assistant", "content": "5 days [1]."}, "done": False},
            {
                "done": True,
                "done_reason": "stop",
                "model": "llama3.2",
                "prompt_eval_count": 120,
                "eval_count": 9,
            },
        ]
        return httpx.Response(200, content="\n".join(json.dumps(line) for line in lines).encode())

    events = await collect(ollama_provider(handler), prompt())

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Refunds take ", "5 days [1]."]
    assert events[-1] == Completed(
        stop_reason=StopReason.END_TURN,
        model="llama3.2",
        usage=providers.Usage(input_tokens=120, output_tokens=9),
    )
    assert seen["stream"] is True
    assert seen["keep_alive"] == "5m"
    assert seen["messages"][0]["role"] == "system"
    assert [m["role"] for m in seen["messages"][1:]] == ["user", "assistant", "user"]


async def test_ollama_length_stop_maps_to_max_tokens() -> None:
    body = json.dumps({"done": True, "done_reason": "length", "eval_count": 1})

    events = await collect(
        ollama_provider(lambda request: httpx.Response(200, content=body.encode())), prompt()
    )

    assert events[-1].stop_reason == StopReason.MAX_TOKENS


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, content=b"model crashed"),
        httpx.Response(200, content=json.dumps({"error": "model not found"}).encode()),
        httpx.Response(200, content=b"not json"),
        httpx.Response(200, content=json.dumps({"message": {"content": "partial"}}).encode()),
    ],
)
async def test_ollama_failures_raise_provider_errors(response: httpx.Response) -> None:
    with pytest.raises(ProviderError):
        await collect(ollama_provider(lambda request: response), prompt())


async def test_ollama_connection_failures_raise_provider_errors() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    with pytest.raises(ProviderError):
        await collect(ollama_provider(handler), prompt())


# Claude


class FakeStream:
    def __init__(self, texts: list[str], final: Any, error: Exception | None = None) -> None:
        self._texts, self._final, self._error = texts, final, error

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    @property
    async def text_stream(self) -> Any:
        for text in self._texts:
            yield text
        if self._error is not None:
            raise self._error

    async def get_final_message(self) -> Any:
        return self._final


class FakeMessages:
    def __init__(self, stream: FakeStream | None = None, error: Exception | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._stream, self._error = stream, error

    def stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        assert self._stream is not None
        return self._stream


def final_message(stop_reason: str = "end_turn", model: str = "claude-opus-5-5", text: str = "") -> Any:
    return SimpleNamespace(
        stop_reason=stop_reason,
        model=model,
        content=[SimpleNamespace(type="text", text=text)] if text else [],
        stop_details=SimpleNamespace(category="cyber") if stop_reason == "refusal" else None,
        usage=SimpleNamespace(
            input_tokens=1200, output_tokens=80, cache_read_input_tokens=900, cache_creation_input_tokens=None
        ),
    )


def fake_client(messages: FakeMessages) -> Any:
    return SimpleNamespace(beta=SimpleNamespace(messages=messages))


@pytest.fixture
def claude_defaults(settings: Any) -> None:
    """The documented defaults from backend/.env.example, pinned so a variable exported
    by the developer's shell cannot change what this test checks."""
    settings.CLAUDE_MODEL = "claude-opus-5-5"
    settings.CLAUDE_FALLBACK_MODEL = "claude-opus-4-8"
    settings.CLAUDE_MAX_TOKENS = 4096
    settings.CLAUDE_EFFORT = "low"


@pytest.mark.usefixtures("claude_defaults")
async def test_claude_request_matches_the_documented_shape() -> None:
    messages = FakeMessages(
        FakeStream(["Refunds take ", "5 days [1]."], final_message(text="Refunds take 5 days [1]."))
    )
    request = prompt()

    events = await collect(ClaudeProvider(client=fake_client(messages)), request)

    (call,) = messages.calls
    assert call["model"] == "claude-opus-5-5"
    assert call["max_tokens"] == 4096
    assert call["system"] == [
        {"type": "text", "text": request.system, "cache_control": {"type": "ephemeral"}}
    ]
    assert call["messages"] == [
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": request.messages[-1].content},
    ]
    assert call["output_config"] == {"effort": "low"}
    assert call["betas"] == ["server-side-fallback-2026-06-01"]
    assert call["fallbacks"] == [{"model": "claude-opus-4-8"}]
    for forbidden in ("thinking", "temperature", "top_p", "top_k"):
        assert forbidden not in call
    assert call["messages"][-1]["role"] == "user"  # no assistant prefill

    assert [e.text for e in events if isinstance(e, TextDelta)] == ["Refunds take ", "5 days [1]."]
    completed = events[-1]
    assert completed.stop_reason == StopReason.END_TURN
    assert completed.text == "Refunds take 5 days [1]."
    assert completed.usage == providers.Usage(
        input_tokens=1200, output_tokens=80, cache_read_input_tokens=900, cache_creation_input_tokens=0
    )


@pytest.mark.usefixtures("claude_defaults")
async def test_claude_refusals_are_reported_without_their_partial_text() -> None:
    final = final_message(stop_reason="refusal", model="claude-opus-4-8", text="Partial")
    messages = FakeMessages(FakeStream(["Partial"], final))

    events = await collect(ClaudeProvider(client=fake_client(messages)), prompt())

    completed = events[-1]
    assert completed.stop_reason == StopReason.REFUSAL
    assert completed.text is None
    assert completed.model == "claude-opus-4-8"  # the served model, not the requested one


async def test_claude_max_tokens_is_reported() -> None:
    messages = FakeMessages(FakeStream(["Long"], final_message(stop_reason="max_tokens", text="Long")))

    events = await collect(ClaudeProvider(client=fake_client(messages)), prompt())

    assert events[-1].stop_reason == StopReason.MAX_TOKENS


def _api_request() -> httpx2.Request:
    # The anthropic SDK is built on httpx2, so its errors carry httpx2 objects.
    return httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


@pytest.mark.parametrize(
    "error",
    [
        anthropic.AuthenticationError(
            "bad key", response=httpx2.Response(401, request=_api_request()), body=None
        ),
        anthropic.RateLimitError(
            "slow down", response=httpx2.Response(429, request=_api_request()), body=None
        ),
        anthropic.APIStatusError(
            "overloaded", response=httpx2.Response(529, request=_api_request()), body=None
        ),
        anthropic.APIConnectionError(request=_api_request()),
    ],
)
async def test_claude_sdk_errors_become_provider_errors(error: Exception) -> None:
    with pytest.raises(ProviderError):
        await collect(ClaudeProvider(client=fake_client(FakeMessages(error=error))), prompt())


async def test_claude_errors_mid_stream_become_provider_errors() -> None:
    error = anthropic.APIConnectionError(request=_api_request())
    messages = FakeMessages(FakeStream(["Refunds"], final_message(), error=error))

    with pytest.raises(ProviderError):
        await collect(ClaudeProvider(client=fake_client(messages)), prompt())


async def test_the_shared_client_reads_the_key_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    created: list[tuple[Any, ...]] = []

    class RecordingClient:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            created.append((args, kwargs))

    monkeypatch.setattr(anthropic, "AsyncAnthropic", RecordingClient)
    monkeypatch.setattr(providers.claude, "_clients", type(providers.claude._clients)())

    first = providers.claude.shared_client()
    second = providers.claude.shared_client()

    assert first is second
    assert created == [((), {})]  # no key passed in code


# Selection


@pytest.mark.parametrize(
    ("configured", "key", "ollama_up", "expected"),
    [
        ("extractive", "sk-test", True, "extractive"),
        ("claude", "sk-test", False, "claude"),
        ("claude", "", True, "extractive"),
        ("ollama", "", True, "ollama"),
        ("ollama", "", False, "extractive"),
        ("auto", "sk-test", True, "ollama"),
        ("auto", "sk-test", False, "extractive"),
    ],
)
def test_provider_selection(settings: Any, configured: str, key: str, ollama_up: bool, expected: str) -> None:
    settings.LLM_PROVIDER = configured
    settings.ANTHROPIC_API_KEY = key
    settings.OLLAMA_MODEL = "llama3.2"
    status = ollama.OllamaStatus(
        reachable=ollama_up, models=frozenset({"llama3.2:latest"} if ollama_up else ())
    )

    assert choose_provider(status).name == expected


async def test_resolve_provider_skips_the_probe_when_not_needed(
    settings: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    settings.LLM_PROVIDER = "extractive"

    async def fail() -> None:
        raise AssertionError("probed")

    monkeypatch.setattr(ollama, "aprobe", fail)

    assert (await providers.resolve_provider()).name == "extractive"
