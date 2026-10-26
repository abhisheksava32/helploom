"""Forwarding a streamed answer over a websocket, one answer at a time per socket.

A chat socket forwards the frames that assistant.services.stream_answer yields.
AnswerStreamMixin runs that iteration in its own task, so the consumer keeps reading
frames (ping, chat.cancel) while an answer streams.

Stopping is cooperative. Only the pipeline can end an answer properly (store it as
truncated, report usage, send message.done), so the mixin asks it to stop through
cancel_streaming_answer(), which the consumer wires to the pipeline's cancel function
(assistant.services.cancel_answer). When the socket closes, the mixin asks the same
way and waits a few seconds for the answer to be saved before cancelling the task.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import AsyncIterator, Callable
from typing import Any

logger = logging.getLogger(__name__)


class AnswerStreamMixin:
    """Mix into an AsyncJsonWebsocketConsumer that has send_json and send_error."""

    # How long a closed socket waits for the pipeline to save a truncated answer.
    disconnect_grace_seconds: float = 5.0

    _answer_task: asyncio.Task[None] | None = None
    _answer_message_id: str | None = None
    _answer_socket_closed: bool = False

    send_json: Callable[..., Any]
    send_error: Callable[..., Any]

    def cancel_streaming_answer(self, message_id: str) -> None:
        """Ask the pipeline to stop the answer with this id. Override to wire it up."""

    @property
    def is_streaming(self) -> bool:
        return self._answer_task is not None and not self._answer_task.done()

    @property
    def streaming_message_id(self) -> str | None:
        return self._answer_message_id if self.is_streaming else None

    def start_answer_stream(
        self, open_stream: Callable[[], AsyncIterator[dict[str, Any]]], **context: Any
    ) -> None:
        """Start forwarding. open_stream is called inside the task, so a pipeline that
        fails on call is reported like one that fails mid stream. context (for example
        client_message_id) is attached to the answer_failed frame."""
        self._answer_message_id = None
        self._answer_task = asyncio.create_task(self._pump_answer(open_stream, context))

    def request_answer_cancel(self, message_id: str | None) -> bool:
        """Handle chat.cancel. A stale or unknown id is ignored: the answer it names has
        usually just finished."""
        current = self.streaming_message_id
        if current is None or (message_id is not None and message_id != current):
            return False
        self.cancel_streaming_answer(current)
        return True

    async def stop_answer_stream(self) -> None:
        """Call on disconnect."""
        self._answer_socket_closed = True
        task = self._answer_task
        if task is None or task.done():
            return
        if self._answer_message_id is not None:
            self.cancel_streaming_answer(self._answer_message_id)
        try:
            await asyncio.wait_for(asyncio.shield(task), timeout=self.disconnect_grace_seconds)
        except TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _pump_answer(
        self, open_stream: Callable[[], AsyncIterator[dict[str, Any]]], context: dict[str, Any]
    ) -> None:
        try:
            async for frame in open_stream():
                if frame.get("type") == "message.start":
                    self._answer_message_id = str(frame.get("message_id") or "") or None
                # After a disconnect the stream is still drained, so the pipeline can
                # finish saving, but nothing is sent.
                if not self._answer_socket_closed:
                    await self.send_json(frame)
        except asyncio.CancelledError:
            raise
        except Exception:
            # stream_answer reports expected failures as frames; this guards bugs.
            logger.exception("Answer stream failed")
            if not self._answer_socket_closed:
                extra = dict(context)
                if self._answer_message_id:
                    extra["message_id"] = self._answer_message_id
                await self.send_error(
                    "answer_failed", "We could not finish this answer. Please try again.", **extra
                )
        finally:
            self._answer_message_id = None
