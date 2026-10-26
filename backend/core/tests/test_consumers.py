"""The dashboard event socket: auth handshake and live event forwarding."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from accounts.models import Membership
from core.consumers import CloseCode
from core.realtime import abroadcast_org_event, broadcast_org_event
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


async def connect_and_auth(membership: Membership) -> WebsocketCommunicator:
    token = await database_sync_to_async(access_token_for)(membership.user)
    socket = WebsocketCommunicator(application, "/ws/dashboard/", headers=[DASHBOARD_ORIGIN])
    connected, _ = await socket.connect()
    assert connected
    await socket.send_json_to({"type": "auth", "token": token, "organization_id": None})
    assert (await socket.receive_json_from())["type"] == "auth.ok"
    return socket


@pytest.mark.django_db(transaction=True)
async def test_events_published_from_worker_threads_reach_the_socket(
    make_member: Callable[..., Membership],
) -> None:
    membership = await database_sync_to_async(make_member)()
    socket = await connect_and_auth(membership)
    event = {"type": "document.status", "document": {"id": "d2", "status": "processing"}}

    # Ingestion runs in a thread pool; the in-memory layer must be reached through the
    # server loop.
    await asyncio.to_thread(broadcast_org_event, membership.organization_id, event)

    assert await socket.receive_json_from(timeout=2) == event
    await socket.disconnect()


@pytest.mark.django_db(transaction=True)
async def test_events_stay_inside_their_organization(make_member: Callable[..., Membership]) -> None:
    mine = await database_sync_to_async(make_member)()
    other = await database_sync_to_async(make_member)()
    socket = await connect_and_auth(mine)

    await abroadcast_org_event(other.organization_id, {"type": "document.deleted", "document_id": "x"})

    assert await socket.receive_nothing(timeout=0.2)
    await socket.disconnect()


async def test_sockets_that_never_authenticate_are_closed(settings: Any) -> None:
    settings.WEBSOCKET_AUTH_TIMEOUT_SECONDS = 0.05
    socket = WebsocketCommunicator(application, "/ws/dashboard/", headers=[DASHBOARD_ORIGIN])
    await socket.connect()

    error = await socket.receive_json_from(timeout=1)

    assert error == {
        "type": "error",
        "code": "auth_timeout",
        "message": "Authenticate within the time limit.",
        "details": {},
    }
    assert (await socket.receive_output(timeout=1))["code"] == CloseCode.AUTH_TIMEOUT


async def test_frames_before_auth_close_the_socket() -> None:
    socket = WebsocketCommunicator(application, "/ws/dashboard/", headers=[DASHBOARD_ORIGIN])
    await socket.connect()

    await socket.send_json_to({"type": "subscribe"})

    assert (await socket.receive_json_from())["code"] == "not_authenticated"
    assert (await socket.receive_output())["code"] == CloseCode.UNAUTHENTICATED
