"""Public widget socket: ws/widget/?site_key=<key>&visitor_id=<id>. Protocol: docs/API.md,
"ws/widget/".

No auth frame: the site key names the organisation, and the organisation is never
taken from the client. The handshake checks run in widget.services.admit_connection;
after that every frame re-reads the widget, so rotating the key or turning the widget
off takes effect on the visitor's next frame. Answers are produced by
assistant.services and forwarded unchanged.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import replace
from typing import Any
from urllib.parse import parse_qs
from uuid import UUID

from rest_framework import serializers as drf_serializers
from rest_framework.exceptions import APIException

from assistant import services as assistant_services
from core.consumers import CloseCode, JsonWebsocketConsumer
from core.origins import normalize_origin, scope_origin
from core.ratelimit import hash_ip, scope_client_ip
from core.realtime import remember_server_loop
from core.streaming import AnswerStreamMixin

from . import services
from .serializers import (
    CancelFrameSerializer,
    ChatMessageFrameSerializer,
    FeedbackFrameSerializer,
    HandoffFrameSerializer,
    ResumeFrameSerializer,
)

logger = logging.getLogger(__name__)

Handler = Callable[[dict[str, Any]], Awaitable[None]]


def _query_param(scope: dict[str, Any], name: str) -> str | None:
    values = parse_qs(scope.get("query_string", b"").decode("latin-1")).get(name)
    return values[0] if values else None


def _header(scope: dict[str, Any], name: bytes) -> str:
    for key, value in scope.get("headers", []):
        if key == name:
            return str(value.decode("latin-1"))
    return ""


class WidgetConsumer(AnswerStreamMixin, JsonWebsocketConsumer):
    site_key: str = ""
    organization_id: UUID | None = None
    ip: str = ""
    visitor: assistant_services.VisitorContext | None = None

    async def connect(self) -> None:
        remember_server_loop()
        site_key = _query_param(self.scope, "site_key")
        origin = scope_origin(self.scope)
        self.ip = scope_client_ip(self.scope)

        admission = await services.admit_connection(site_key=site_key, origin=origin, ip=self.ip)
        if admission.outcome == services.Admission.ORIGIN_NOT_ALLOWED:
            # Rejected before accept: the browser only sees a failed connection, so a
            # foreign site learns nothing about the widget.
            await self.close(code=CloseCode.FORBIDDEN)
            return

        await self.accept()
        if admission.outcome == services.Admission.THROTTLED:
            await self.send_error(
                "throttled",
                "Too many connections from your network. Please wait a minute.",
                details={"retry_after": admission.retry_after},
            )
            await self.close(code=CloseCode.RATE_LIMITED)
            return
        widget = admission.widget
        if admission.outcome != services.Admission.OK or widget is None or site_key is None:
            await self._reject_site_key()
            return

        self.site_key = site_key
        self.organization_id = widget.organization_id
        self.visitor = assistant_services.VisitorContext(
            visitor_id=services.clean_visitor_id(_query_param(self.scope, "visitor_id")),
            origin=normalize_origin(origin) or "",
            ip_hash=hash_ip(self.ip),
            user_agent=_header(self.scope, b"user-agent")[:300],
        )
        await self.send_json(
            {
                "type": "session.ready",
                "visitor_id": self.visitor.visitor_id,
                "organization_name": widget.organization.name,
                "title": widget.title,
                "greeting": widget.greeting,
                "brand_color": widget.brand_color,
                "position": widget.position,
            }
        )

    async def disconnect(self, code: int) -> None:
        await self.stop_answer_stream()

    def cancel_streaming_answer(self, message_id: str) -> None:
        # The pipeline stops at its next token and finishes with message.done (truncated).
        assistant_services.cancel_answer(message_id)

    async def _reject_site_key(self) -> None:
        await self.send_error("invalid_site_key", "This widget does not exist or is turned off.")
        await self.close(code=CloseCode.NOT_FOUND)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        if self.visitor is None or self.organization_id is None:
            return  # handshake was refused; the socket is closing
        widget = await services.aget_active_widget(self.site_key)
        if widget is None or widget.organization_id != self.organization_id:
            await self._reject_site_key()
            return
        handlers: dict[str, Handler] = {
            "chat.message": self.on_chat_message,
            "chat.cancel": self.on_chat_cancel,
            "conversation.resume": self.on_resume,
            "feedback": self.on_feedback,
            "handoff.request": self.on_handoff,
        }
        handler = handlers.get(content["type"])
        if handler is None:
            await self.send_error("unknown_type", f"Unknown frame type {content['type']!r}.")
            return
        await handler(content)

    async def _validate(
        self, serializer_class: type[drf_serializers.Serializer], content: dict[str, Any], **extra: Any
    ) -> dict[str, Any] | None:
        serializer = serializer_class(data=content)
        try:
            serializer.is_valid(raise_exception=True)
        except drf_serializers.ValidationError as exc:
            await self.send_exception(exc, **extra)
            return None
        return dict(serializer.validated_data)

    async def on_chat_message(self, content: dict[str, Any]) -> None:
        assert self.visitor is not None and self.organization_id is not None
        raw_id = content.get("client_message_id")
        echo = {"client_message_id": raw_id} if isinstance(raw_id, str) else {}

        # Counted before validation, so malformed frames cannot be used to flood.
        limit = await services.check_message_rate(self.ip)
        if not limit.allowed:
            await self.send_error(
                "throttled",
                "You are sending messages too fast.",
                details={"retry_after": limit.retry_after},
                **echo,
            )
            return
        if self.is_streaming:
            await self.send_error("busy", "Please wait for the current answer to finish.", **echo)
            return
        frame = await self._validate(ChatMessageFrameSerializer, content, **echo)
        if frame is None:
            return

        request = assistant_services.AskRequest(
            organization_id=self.organization_id,
            channel="widget",
            content=frame["content"],
            client_message_id=frame["client_message_id"],
            conversation_id=frame["conversation_id"],
            visitor=replace(self.visitor, page_url=frame.get("page_url", "")),
        )
        # Looked up at call time so the pipeline can be swapped in tests.
        self.start_answer_stream(
            lambda: assistant_services.stream_answer(request),
            client_message_id=frame["client_message_id"],
        )

    async def on_chat_cancel(self, content: dict[str, Any]) -> None:
        frame = await self._validate(CancelFrameSerializer, content)
        if frame is not None:
            self.request_answer_cancel(frame["message_id"])

    async def on_resume(self, content: dict[str, Any]) -> None:
        frame = await self._validate(ResumeFrameSerializer, content)
        if frame is None:
            return
        await self._call_assistant(
            self._history(frame["conversation_id"]), conversation_id=str(frame["conversation_id"])
        )

    async def _history(self, conversation_id: UUID) -> dict[str, Any]:
        assert self.visitor is not None and self.organization_id is not None
        history = await assistant_services.conversation_history(
            organization_id=self.organization_id,
            conversation_id=conversation_id,
            visitor_id=self.visitor.visitor_id,
        )
        if history is None:
            return {
                "type": "error",
                "code": "not_found",
                "message": "We could not find that conversation. Starting a new one.",
                "details": {},
                "conversation_id": str(conversation_id),
            }
        return history

    async def on_feedback(self, content: dict[str, Any]) -> None:
        assert self.visitor is not None and self.organization_id is not None
        frame = await self._validate(FeedbackFrameSerializer, content)
        if frame is None:
            return
        await self._call_assistant(
            assistant_services.record_feedback(
                organization_id=self.organization_id,
                message_id=frame["message_id"],
                rating=frame["rating"],
                comment=frame["comment"],
                visitor_id=self.visitor.visitor_id,
            ),
            message_id=str(frame["message_id"]),
        )

    async def on_handoff(self, content: dict[str, Any]) -> None:
        assert self.visitor is not None and self.organization_id is not None
        frame = await self._validate(HandoffFrameSerializer, content)
        if frame is None:
            return
        await self._call_assistant(
            assistant_services.create_handoff_ticket(
                organization_id=self.organization_id,
                conversation_id=frame["conversation_id"],
                email=frame["email"],
                name=frame["name"],
                note=frame["note"],
                visitor_id=self.visitor.visitor_id,
            )
        )

    async def _call_assistant(self, call: Awaitable[dict[str, Any] | None], **extra: Any) -> None:
        """Send the reply frame, or the service's failure as an error frame."""
        try:
            reply = await call
        except APIException as exc:
            await self.send_exception(exc, **extra)
            return
        except Exception:
            logger.exception("Widget request failed")
            await self.send_error(
                "server_error", "Something went wrong on our side. Please try again.", **extra
            )
            return
        if reply is not None:
            await self.send_json(reply)
