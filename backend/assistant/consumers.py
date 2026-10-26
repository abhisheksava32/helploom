"""Dashboard playground chat socket. Protocol: docs/API.md, "ws/chat/".

Authentication (the auth frame), ping and the error frame shape
come from core.consumers.AuthenticatedJsonConsumer. This consumer runs one answer at
a time per socket in a background task, so the socket keeps reading frames
(chat.cancel, ping) while an answer streams, and forwards the frames of
assistant.services.stream_answer unchanged.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import Any
from uuid import UUID

from rest_framework.exceptions import NotFound, ValidationError

from core.consumers import AuthenticatedJsonConsumer

from . import services

logger = logging.getLogger(__name__)

CLIENT_MESSAGE_ID_MAX = 64


def _uuid_or_none(value: Any) -> UUID | None:
    if value is None:
        return None
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise ValueError("Not a valid id.") from exc


class ChatConsumer(AuthenticatedJsonConsumer):
    _answer_task: asyncio.Task[None] | None = None
    _streaming_message_id: str | None = None
    _closed: bool = False

    async def handle_message(self, content: dict[str, Any]) -> None:
        kind = content["type"]
        if kind == "chat.message":
            await self._ask(content)
        elif kind == "chat.cancel":
            await self._cancel(content)
        elif kind == "handoff.request":
            await self._handoff(content)
        else:
            await super().handle_message(content)

    async def _ask(self, content: dict[str, Any]) -> None:
        client_message_id = content.get("client_message_id")
        if not isinstance(client_message_id, str) or not 0 < len(client_message_id) <= CLIENT_MESSAGE_ID_MAX:
            await self.send_error(
                "validation_error",
                "client_message_id is required (up to 64 characters).",
                details={"client_message_id": ["This field is required."]},
            )
            return
        if self._answer_task is not None and not self._answer_task.done():
            await self.send_error(
                "busy",
                "Wait for the current answer to finish.",
                details={},
                client_message_id=client_message_id,
            )
            return
        try:
            conversation_id = _uuid_or_none(content.get("conversation_id"))
        except ValueError:
            await self.send_error(
                "validation_error",
                "conversation_id must be an id or null.",
                details={"conversation_id": ["Not a valid id."]},
                client_message_id=client_message_id,
            )
            return
        assert self.membership is not None
        question = content.get("content")
        request = services.AskRequest(
            organization_id=self.membership.organization_id,
            channel="playground",
            content=question if isinstance(question, str) else "",
            client_message_id=client_message_id,
            conversation_id=conversation_id,
            user_id=self.membership.user_id,
        )
        self._answer_task = asyncio.create_task(self._stream(request))

    async def _stream(self, request: services.AskRequest) -> None:
        try:
            async for frame in services.stream_answer(request):
                if frame["type"] == "message.start":
                    self._streaming_message_id = frame["message_id"]
                if not self._closed:
                    await self.send_json(frame)
        except Exception:
            # stream_answer turns expected failures into frames; this is a bug guard.
            logger.exception("Playground answer crashed")
            if not self._closed:
                await self.send_error(
                    "answer_failed",
                    "Something went wrong while answering. Please try again.",
                    details={},
                    client_message_id=request.client_message_id,
                )
        finally:
            self._streaming_message_id = None

    async def _cancel(self, content: dict[str, Any]) -> None:
        message_id = content.get("message_id")
        # Only the answer this socket is streaming can be stopped from here.
        if isinstance(message_id, str) and message_id == self._streaming_message_id:
            services.cancel_answer(message_id)

    async def _handoff(self, content: dict[str, Any]) -> None:
        assert self.membership is not None
        try:
            conversation_id = _uuid_or_none(content.get("conversation_id"))
            if conversation_id is None:
                raise ValueError
        except ValueError:
            await self.send_error(
                "validation_error",
                "conversation_id is required.",
                details={"conversation_id": ["This field is required."]},
            )
            return
        try:
            frame = await services.create_handoff_ticket(
                organization_id=self.membership.organization_id,
                conversation_id=conversation_id,
                email=str(content.get("email") or ""),
                name=str(content.get("name") or ""),
                note=str(content.get("note") or ""),
            )
        except ValidationError as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {"non_field_errors": exc.detail}
            await self.send_error("validation_error", services.first_error_message(detail), details=detail)
            return
        except NotFound:
            await self.send_error("not_found", "This conversation does not exist.", details={})
            return
        await self.send_json(frame)

    async def on_disconnect(self, code: int) -> None:
        self._closed = True
        # Let the pipeline finish and save a truncated answer instead of killing it
        # mid-write; it stops at its next delta.
        if self._streaming_message_id is not None:
            services.cancel_answer(self._streaming_message_id)
        if self._answer_task is not None and not self._answer_task.done():
            with contextlib.suppress(asyncio.TimeoutError, asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(self._answer_task), timeout=5)
