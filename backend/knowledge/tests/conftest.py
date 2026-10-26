"""Fixtures for the knowledge tests: offline embedders, private media and captured
real time events."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from knowledge import ollama


@pytest.fixture(autouse=True)
def offline_ollama() -> Iterator[None]:
    """Nothing in the suite may reach a real Ollama, even when one runs locally."""
    ollama.set_probe_result(ollama.OllamaStatus(reachable=False, detail="Not reachable (tests)."))
    yield
    ollama.reset_probe_cache()


@pytest.fixture(autouse=True)
def private_media(settings: Any, tmp_path: Path) -> Path:
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.MEDIA_ROOT


@pytest.fixture
def broadcasts(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Every event knowledge.services publishes, in order."""
    events: list[tuple[str, dict[str, Any]]] = []

    def record(organization_id: Any, event: dict[str, Any]) -> None:
        events.append((str(organization_id), event))

    monkeypatch.setattr("knowledge.services.broadcast_org_event", record)
    return events
