"""The dashboard event socket: auth handshake and live event forwarding."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from accounts.models import Membership
from core.consumers import CloseCode
from core.realtime import abroadcast_org_event
from core.testing import access_token_for
from helploom.asgi import application

DASHBOARD_ORIGIN = (b"origin", b"http://localhost:3000")


@pytest.mark.django_db(transaction=True)
async def test_dashboard_socket_authenticates_and_forwards_events(
    make_member: Callable[..., Membership],
) -> None:
    membership = await database_sync_to_async(make_member)()
    token = await database_sync_to_async(access_token_for)(membership.user)
    socket = WebsocketCommunicator(application, "/ws/dashboard/", headers=[DASHBOARD_ORIGIN])
    connected, _ = await socket.connect()
    assert connected

    await socket.send_json_to(
        {"type": "auth", "token": token, "organization_id": str(membership.organization_id)}
    )
    ok = await socket.receive_json_from()
    assert ok == {
        "type": "auth.ok",
        "user_id": str(membership.user_id),
        "organization_id": str(membership.organization_id),
        "role": "owner",
    }

    event = {"type": "document.status", "document": {"id": "d1", "status": "ready"}}
    await abroadcast_org_event(membership.organization_id, event)
    assert await socket.receive_json_from() == event

    await socket.send_json_to({"type": "ping"})
    assert await socket.receive_json_from() == {"type": "pong"}
    await socket.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_dashboard_socket_rejects_a_bad_token() -> None:
    socket = WebsocketCommunicator(application, "/ws/dashboard/", headers=[DASHBOARD_ORIGIN])
    await socket.connect()

    await socket.send_json_to({"type": "auth", "token": "garbage", "organization_id": None})

    error = await socket.receive_json_from()
    assert error["type"] == "error"
    assert error["code"] == "authentication_failed"
    assert (await socket.receive_output())["code"] == CloseCode.UNAUTHENTICATED


async def test_dashboard_socket_rejects_foreign_origins() -> None:
    socket = WebsocketCommunicator(
        application, "/ws/dashboard/", headers=[(b"origin", b"https://evil.example")]
    )

    connected, code = await socket.connect()

    assert not connected
    assert code == CloseCode.FORBIDDEN
