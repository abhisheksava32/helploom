"""Fixtures for the assistant tests: offline providers, a small knowledge base,
captured real time events and scripted providers for the pipeline."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncGenerator, Iterator, Sequence
from pathlib import Path
from typing import Any

import pytest

from accounts.models import Organization
from assistant.prompts import Prompt
from assistant.providers import Completed, ProviderError, ProviderEvent, StopReason, TextDelta, Usage
from knowledge import ollama
from knowledge.models import Document
from knowledge.tests.factories import REFUND_POLICY, SHIPPING_FAQ, ingest


@pytest.fixture(autouse=True)
def offline_ollama() -> Iterator[None]:
    ollama.set_probe_result(ollama.OllamaStatus(reachable=False, detail="Not reachable (tests)."))
    yield
    ollama.reset_probe_cache()


@pytest.fixture(autouse=True)
def private_media(settings: Any, tmp_path: Path) -> Path:
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def knowledge_base(organization: Organization) -> dict[str, Document]:
    return {
        "refunds": ingest(organization, "refund-policy.md", REFUND_POLICY),
        "shipping": ingest(organization, "shipping-faq.md", SHIPPING_FAQ),
    }


@pytest.fixture
def org_events(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Events assistant.services publishes, sync or async."""
    events: list[dict[str, Any]] = []

    def record(organization_id: Any, event: dict[str, Any]) -> None:
        events.append({"organization_id": str(organization_id), **event})

    async def arecord(organization_id: Any, event: dict[str, Any]) -> None:
        record(organization_id, event)

    monkeypatch.setattr("assistant.services.broadcast_org_event", record)
    monkeypatch.setattr("assistant.services.abroadcast_org_event", arecord)
    return events


class ScriptedProvider:
    """A provider that replays a script: text deltas, then a Completed event, or an
    error part way through. Records every prompt it was asked to answer."""

    def __init__(
        self,
        deltas: Sequence[str] = ("Refunds take 5 business days [1].",),
        *,
        name: str = "claude",
        model: str = "claude-opus-5-5",
        stop_reason: str = StopReason.END_TURN,
        usage: Usage | None = None,
        fail_after: int | None = None,
        delay: float = 0.0,
    ) -> None:
        self.name = name
        self.model = model
        self.deltas = list(deltas)
        self.stop_reason = stop_reason
        self.usage = usage or Usage()
        self.fail_after = fail_after
        self.delay = delay
        self.prompts: list[Prompt] = []

    async def is_available(self) -> bool:
        return True

    async def stream(self, prompt: Prompt) -> AsyncGenerator[ProviderEvent]:
        self.prompts.append(prompt)
        for index, delta in enumerate(self.deltas):
            if self.fail_after is not None and index >= self.fail_after:
                raise ProviderError("scripted failure")
            if self.delay:
                await asyncio.sleep(self.delay)
            yield TextDelta(delta)
        if self.fail_after is not None and self.fail_after >= len(self.deltas):
            raise ProviderError("scripted failure")
        yield Completed(stop_reason=self.stop_reason, model=self.model, usage=self.usage)


@pytest.fixture
def use_provider(monkeypatch: pytest.MonkeyPatch) -> Any:
    """Make the pipeline answer with the given provider."""

    def install(provider: Any) -> Any:
        async def resolve() -> Any:
            return provider

        monkeypatch.setattr("assistant.services.resolve_provider", resolve)
        return provider

    return install
