"""Websocket base classes and the dashboard event socket.

Authenticated dashboard sockets (ws/dashboard/ here, ws/chat/ in the assistant app)
share AuthenticatedJsonConsumer. The first frame must be
{"type": "auth", "token": "<access JWT>", "organization_id": "<uuid or null>"}.
Sending the token in a frame rather than the URL keeps it out of proxy and server
access logs. Unauthenticated sockets are closed after
WEBSOCKET_AUTH_TIMEOUT_SECONDS.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from enum import IntEnum
from typing import TYPE_CHECKING, Any

from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from django.conf import settings
from rest_framework.exceptions import APIException
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.tokens import AccessToken

from core.exceptions import error_frame
from core.origins import origin_allowed, scope_origin
from core.realtime import org_group, remember_server_loop
from core.tenancy import resolve_membership

if TYPE_CHECKING:
    from accounts.models import Membership


class CloseCode(IntEnum):
    BAD_REQUEST = 4400
    UNAUTHENTICATED = 4401
    FORBIDDEN = 4403
    NOT_FOUND = 4404
    AUTH_TIMEOUT = 4408
    RATE_LIMITED = 4429
    INTERNAL_ERROR = 1011


@database_sync_to_async
def authenticate_membership(token: Any, organization_id: Any) -> Membership | None:
    from accounts.models import User

    if not isinstance(token, str) or not token:
        return None
    try:
        access = AccessToken(token)  # type: ignore[arg-type]
    except TokenError:
        return None
    user_id = access.get(jwt_settings.USER_ID_CLAIM)
    user = User.objects.filter(id=user_id, is_active=True).first()
    if user is None:
        return None
    org = organization_id if isinstance(organization_id, str) and organization_id else None
    return resolve_membership(user, org)


class JsonWebsocketConsumer(AsyncJsonWebsocketConsumer):
    """Adds tolerant JSON decoding, ping/pong and a uniform error frame."""

    async def receive(
        self, text_data: str | None = None, bytes_data: bytes | None = None, **kwargs: Any
    ) -> None:
        if text_data is None:
            await self.send_error("bad_request", "Send JSON text frames.")
            return
        try:
            content = json.loads(text_data)
        except json.JSONDecodeError:
            await self.send_error("bad_request", "Frames must be valid JSON.")
            return
        if not isinstance(content, dict) or not isinstance(content.get("type"), str):
            await self.send_error("bad_request", 'Every frame needs a string "type".')
            return
        if content["type"] == "ping":
            await self.send_json({"type": "pong"})
            return
        await self.receive_json(content)

    async def send_error(
        self, code: str, message: str, details: dict[str, Any] | None = None, **extra: Any
    ) -> None:
        await self.send_json(
            {"type": "error", "code": code, "message": message, "details": details or {}, **extra}
        )

    async def send_exception(self, exc: APIException, **extra: Any) -> None:
        """Report a service exception with the same code and details REST would use."""
        await self.send_json(error_frame(exc, **extra))


class AuthenticatedJsonConsumer(JsonWebsocketConsumer):
    membership: Membership | None = None
    _auth_timer: asyncio.Task[None] | None = None

    async def connect(self) -> None:
        remember_server_loop()
        origin = scope_origin(self.scope)
        # Browsers always send Origin. Auth is a bearer token rather than a cookie, so
        # this is defence in depth, not the main control.
        if origin is not None and not origin_allowed(origin, settings.CORS_ALLOWED_ORIGINS):
            await self.close(code=CloseCode.FORBIDDEN)
            return
        await self.accept()
        self._auth_timer = asyncio.create_task(self._close_if_unauthenticated())

    async def disconnect(self, code: int) -> None:
        if self._auth_timer is not None:
            self._auth_timer.cancel()
        await self.on_disconnect(code)

    async def _close_if_unauthenticated(self) -> None:
        with contextlib.suppress(asyncio.CancelledError):
            await asyncio.sleep(settings.WEBSOCKET_AUTH_TIMEOUT_SECONDS)
            if self.membership is None:
                await self.send_error("auth_timeout", "Authenticate within the time limit.")
                await self.close(code=CloseCode.AUTH_TIMEOUT)

    async def receive_json(self, content: dict[str, Any], **kwargs: Any) -> None:
        kind = content["type"]
        if self.membership is None:
            if kind != "auth":
                await self.send_error("not_authenticated", "Send an auth frame first.")
                await self.close(code=CloseCode.UNAUTHENTICATED)
                return
            await self._authenticate(content)
            return
        if kind == "auth":
            await self.send_error("already_authenticated", "This socket is already authenticated.")
            return
        await self.handle_message(content)

    async def _authenticate(self, content: dict[str, Any]) -> None:
        membership = await authenticate_membership(content.get("token"), content.get("organization_id"))
        if membership is None:
            await self.send_error("authentication_failed", "The token is invalid or expired.")
            await self.close(code=CloseCode.UNAUTHENTICATED)
            return
        if self._auth_timer is not None:
            self._auth_timer.cancel()
        self.membership = membership
        await self.send_json(
            {
                "type": "auth.ok",
                "user_id": str(membership.user_id),
                "organization_id": str(membership.organization_id),
                "role": membership.role,
            }
        )
        await self.on_authenticated()

    @property
    def organization_id(self) -> str:
        assert self.membership is not None
        return str(self.membership.organization_id)

    async def on_authenticated(self) -> None:
        """Hook: join groups, send initial state."""

    async def handle_message(self, content: dict[str, Any]) -> None:
        await self.send_error("unknown_type", f"Unknown frame type {content['type']!r}.")

    async def on_disconnect(self, code: int) -> None:
        """Hook: leave groups, cancel work."""


class DashboardConsumer(AuthenticatedJsonConsumer):
    """ws/dashboard/: joins org.<organization_id> after auth and forwards every event
    published with core.realtime unchanged (document status, new conversations, tickets)."""

    async def on_authenticated(self) -> None:
        await self.channel_layer.group_add(org_group(self.organization_id), self.channel_name)

    async def on_disconnect(self, code: int) -> None:
        if self.membership is not None:
            await self.channel_layer.group_discard(org_group(self.organization_id), self.channel_name)

    async def org_event(self, message: dict[str, Any]) -> None:
        await self.send_json(message["event"])


__all__ = [
    "AuthenticatedJsonConsumer",
    "CloseCode",
    "DashboardConsumer",
    "JsonWebsocketConsumer",
    "authenticate_membership",
]
