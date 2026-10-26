"""The ws/chat/ playground socket: auth, streaming answers, busy, cancel and handoff."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator

from accounts.models import Membership
from assistant.models import Conversation, HandoffTicket
from core.testing import access_token_for
from helploom.asgi import application
from knowledge.models import Document

from .conftest import ScriptedProvider

DASHBOARD_ORIGIN = (b"origin", b"http://localhost:3000")
transactional = pytest.mark.django_db(transaction=True)


@pytest.fixture
async def chat(owner: Membership) -> AsyncIterator[WebsocketCommunicator]:
    token = await database_sync_to_async(access_token_for)(owner.user)
    socket = WebsocketCommunicator(application, "/ws/chat/", headers=[DASHBOARD_ORIGIN])
    connected, _ = await socket.connect()
    assert connected
    await socket.send_json_to({"type": "auth", "token": token, "organization_id": str(owner.organization_id)})
    assert (await socket.receive_json_from())["type"] == "auth.ok"
    yield socket
    await socket.disconnect()


async def receive_until(socket: WebsocketCommunicator, frame_type: str) -> list[dict[str, Any]]:
    frames: list[dict[str, Any]] = []
    while True:
        frame = await socket.receive_json_from(timeout=5)
        frames.append(frame)
        if frame["type"] in (frame_type, "error"):
            return frames


def question(content: str = "How long do refunds take?", **extra: Any) -> dict[str, Any]:
    return {
        "type": "chat.message",
        "client_message_id": "c-17",
        "conversation_id": None,
        "content": content,
        **extra,
    }


@transactional
async def test_chat_streams_an_answer_over_the_socket(
    chat: WebsocketCommunicator, owner: Membership, knowledge_base: dict[str, Document]
) -> None:
    await chat.send_json_to(question())

    frames = await receive_until(chat, "message.done")

    types = [frame["type"] for frame in frames]
    assert types[0] == "message.start"
    assert types[-2:] == ["message.citations", "message.done"]
    assert frames[0]["client_message_id"] == "c-17"
    done = frames[-1]
    assert done["answer_type"] == "answered"
    conversation = await database_sync_to_async(Conversation.objects.get)(pk=done["conversation_id"])
    assert (conversation.channel, conversation.started_by_id) == ("playground", owner.user_id)


@transactional
async def test_one_answer_at_a_time_and_cancel(
    chat: WebsocketCommunicator, knowledge_base: dict[str, Document], use_provider: Any
) -> None:
    use_provider(ScriptedProvider([f"part{i} " for i in range(200)], delay=0.01))
    await chat.send_json_to(question())
    start = await chat.receive_json_from(timeout=5)
    assert start["type"] == "message.start"

    await chat.send_json_to(question("Another one?", client_message_id="c-18"))
    frames = await receive_until(chat, "never")
    busy = frames[-1]
    assert (busy["type"], busy["code"], busy["client_message_id"]) == ("error", "busy", "c-18")

    await chat.send_json_to({"type": "chat.cancel", "message_id": start["message_id"]})
    done = (await receive_until(chat, "message.done"))[-1]
    assert done["type"] == "message.done"
    assert done["status"] == "truncated"


@transactional
async def test_bad_frames_get_validation_errors(chat: WebsocketCommunicator) -> None:
    await chat.send_json_to({"type": "chat.message", "content": "Hi"})
    assert (await chat.receive_json_from())["code"] == "validation_error"

    await chat.send_json_to(question(conversation_id="not-a-uuid"))
    error = await chat.receive_json_from()
    assert (error["code"], error["client_message_id"]) == ("validation_error", "c-17")

    await chat.send_json_to({"type": "telepathy"})
    assert (await chat.receive_json_from())["code"] == "unknown_type"


@transactional
async def test_handoff_over_the_playground_socket(
    chat: WebsocketCommunicator, knowledge_base: dict[str, Document]
) -> None:
    await chat.send_json_to(question())
    done = (await receive_until(chat, "message.done"))[-1]

    await chat.send_json_to(
        {"type": "handoff.request", "conversation_id": done["conversation_id"], "email": "jo@example.net"}
    )
    created = await chat.receive_json_from(timeout=5)

    assert created["type"] == "handoff.created"
    assert created["ticket"]["conversation_id"] == done["conversation_id"]
    assert await database_sync_to_async(HandoffTicket.objects.count)() == 1

    await chat.send_json_to(
        {"type": "handoff.request", "conversation_id": done["conversation_id"], "email": "nope"}
    )
    assert (await chat.receive_json_from())["code"] == "validation_error"


@transactional
async def test_chat_requires_authentication() -> None:
    socket = WebsocketCommunicator(application, "/ws/chat/", headers=[DASHBOARD_ORIGIN])
    await socket.connect()

    await socket.send_json_to(question())

    assert (await socket.receive_json_from())["code"] == "not_authenticated"
    await socket.disconnect()
