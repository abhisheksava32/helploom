"""AnswerStreamMixin: forwarding, one answer at a time, cooperative cancel and cleanup."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import Any

from core.streaming import AnswerStreamMixin


class FakeSocket(AnswerStreamMixin):
    """Records frames and routes cancel requests to an event, like the real pipeline."""

    def __init__(self) -> None:
        self.sent: list[dict[str, Any]] = []
        self.cancelled: list[str] = []
        self.cancel_event = asyncio.Event()

    def cancel_streaming_answer(self, message_id: str) -> None:
        self.cancelled.append(message_id)
        self.cancel_event.set()

    async def send_json(self, content: dict[str, Any]) -> None:
        self.sent.append(content)

    async def send_error(
        self, code: str, message: str, details: dict[str, Any] | None = None, **extra: Any
    ) -> None:
        self.sent.append(
            {"type": "error", "code": code, "message": message, "details": details or {}, **extra}
        )

    async def wait(self) -> None:
        assert self._answer_task is not None
        await self._answer_task


def start(message_id: str = "m1") -> dict[str, Any]:
    return {"type": "message.start", "message_id": message_id}


def cooperative_stream(socket: FakeSocket) -> AsyncIterator[dict[str, Any]]:
    """Streams deltas until asked to stop, then finishes as truncated."""

    async def stream() -> AsyncIterator[dict[str, Any]]:
        yield start()
        while not socket.cancel_event.is_set():
            yield {"type": "message.delta", "message_id": "m1", "delta": "more "}
            await asyncio.sleep(0.005)
        yield {"type": "message.done", "message_id": "m1", "status": "truncated"}

    return stream()


async def test_frames_are_forwarded_in_order() -> None:
    async def stream() -> AsyncIterator[dict[str, Any]]:
        yield start()
        yield {"type": "message.delta", "message_id": "m1", "delta": "Hi"}
        yield {"type": "message.done", "message_id": "m1", "status": "complete"}

    socket = FakeSocket()
    socket.start_answer_stream(stream)
    assert socket.is_streaming
    await socket.wait()

    assert [frame["type"] for frame in socket.sent] == ["message.start", "message.delta", "message.done"]
    assert not socket.is_streaming
    assert socket.streaming_message_id is None


async def test_cancel_asks_the_pipeline_to_stop_the_current_answer() -> None:
    socket = FakeSocket()
    socket.start_answer_stream(lambda: cooperative_stream(socket))
    await asyncio.sleep(0.01)

    assert not socket.request_answer_cancel("someone-else")
    assert socket.request_answer_cancel("m1")
    await socket.wait()

    assert socket.cancelled == ["m1"]
    assert socket.sent[-1] == {"type": "message.done", "message_id": "m1", "status": "truncated"}


async def test_cancel_without_a_running_answer_is_ignored() -> None:
    socket = FakeSocket()

    assert not socket.request_answer_cancel("m1")
    assert socket.cancelled == []


async def test_a_pipeline_that_fails_on_call_reports_answer_failed() -> None:
    def broken() -> AsyncIterator[dict[str, Any]]:
        raise NotImplementedError

    socket = FakeSocket()
    socket.start_answer_stream(broken, client_message_id="c-2")
    await socket.wait()

    assert socket.sent == [
        {
            "type": "error",
            "code": "answer_failed",
            "message": "We could not finish this answer. Please try again.",
            "details": {},
            "client_message_id": "c-2",
        }
    ]


async def test_a_crash_mid_stream_names_the_message() -> None:
    async def stream() -> AsyncIterator[dict[str, Any]]:
        yield start()
        raise RuntimeError("provider exploded")

    socket = FakeSocket()
    socket.start_answer_stream(stream, client_message_id="c-3")
    await socket.wait()

    assert socket.sent[-1]["code"] == "answer_failed"
    assert socket.sent[-1]["message_id"] == "m1"
    assert "exploded" not in socket.sent[-1]["message"]


async def test_disconnect_lets_the_pipeline_save_but_sends_nothing() -> None:
    socket = FakeSocket()
    socket.start_answer_stream(lambda: cooperative_stream(socket))
    await asyncio.sleep(0.01)
    sent_before = len(socket.sent)

    await socket.stop_answer_stream()

    assert socket.cancelled == ["m1"]
    assert not socket.is_streaming
    assert len(socket.sent) == sent_before  # the final frames were drained, not sent


async def test_disconnect_cancels_a_pipeline_that_does_not_stop() -> None:
    cancelled = asyncio.Event()

    async def stubborn() -> AsyncIterator[dict[str, Any]]:
        yield start()
        try:
            await asyncio.sleep(10)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        yield {"type": "message.done"}

    socket = FakeSocket()
    socket.disconnect_grace_seconds = 0.05
    socket.start_answer_stream(stubborn)
    await asyncio.sleep(0.01)

    await socket.stop_answer_stream()

    assert cancelled.is_set()
    assert not socket.is_streaming
