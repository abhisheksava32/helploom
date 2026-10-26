"""The public ws/widget/ socket: handshake order, rate limits, key rotation and frame
routing. The answer pipeline is replaced with fakes, so these tests pin the widget's
side of the contract without depending on retrieval or a model."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from channels.db import database_sync_to_async
from channels.testing import WebsocketCommunicator
from django.core.cache import cache
from rest_framework import exceptions

from accounts.models import Organization
from assistant import services as assistant_services
from core.consumers import CloseCode
from helploom.asgi import application
from widget import services
from widget.models import WidgetConfig

pytestmark = pytest.mark.django_db(transaction=True)

SHOP = "https://shop.example.com"


@pytest.fixture(autouse=True)
def _clear_rate_limits() -> None:
    cache.clear()


@pytest.fixture
def make_widget(make_organization: Callable[..., Organization]) -> Callable[..., Any]:
    async def factory(**changes: Any) -> WidgetConfig:
        def create() -> WidgetConfig:
            widget = services.create_widget(make_organization(name="Northwind Outfitters"))
            return services.update_widget(widget, **{"allowed_origins": [SHOP], **changes})

        return await database_sync_to_async(create)()

    return factory


async def open_socket(
    site_key: str, *, origin: str = SHOP, visitor_id: str | None = None, ip: str = "198.51.100.4"
) -> tuple[WebsocketCommunicator, bool, int | None]:
    path = f"/ws/widget/?site_key={site_key}"
    if visitor_id:
        path += f"&visitor_id={visitor_id}"
    socket = WebsocketCommunicator(
        application, path, headers=[(b"origin", origin.encode()), (b"user-agent", b"pytest-agent")]
    )
    socket.scope["client"] = (ip, 50000)
    connected, code = await socket.connect()
    return socket, connected, code


async def ready_socket(widget: WidgetConfig, **kwargs: Any) -> tuple[WebsocketCommunicator, dict[str, Any]]:
    socket, connected, _ = await open_socket(widget.site_key, **kwargs)
    assert connected
    ready = await socket.receive_json_from()
    assert ready["type"] == "session.ready"
    return socket, ready


def answer_frames(request: Any, text: str = "Refunds take 5 business days [1].") -> list[dict[str, Any]]:
    return [
        {"type": "message.start", "client_message_id": request.client_message_id, "message_id": "m1"},
        {"type": "message.delta", "message_id": "m1", "delta": text},
        {"type": "message.citations", "message_id": "m1", "citations": []},
        {"type": "message.done", "message_id": "m1", "status": "complete", "content": text},
    ]


@pytest.fixture
def pipeline(monkeypatch: pytest.MonkeyPatch) -> list[Any]:
    """A pipeline that answers instantly and records each AskRequest."""
    requests: list[Any] = []

    async def stream_answer(request: Any) -> AsyncIterator[dict[str, Any]]:
        requests.append(request)
        for frame in answer_frames(request):
            yield frame

    monkeypatch.setattr(assistant_services, "stream_answer", stream_answer)
    return requests


# Handshake


async def test_handshake_sends_session_ready(make_widget: Callable[..., Any]) -> None:
    widget = await make_widget(title="Northwind help", brand_color="#0f766e")

    socket, ready = await ready_socket(widget, visitor_id="v_known_visitor_123")

    assert ready == {
        "type": "session.ready",
        "visitor_id": "v_known_visitor_123",
        "organization_name": "Northwind Outfitters",
        "title": "Northwind help",
        "greeting": widget.greeting,
        "brand_color": "#0f766e",
        "position": "right",
    }
    await socket.send_json_to({"type": "ping"})
    assert await socket.receive_json_from() == {"type": "pong"}
    await socket.disconnect()


async def test_a_bad_visitor_id_is_replaced(make_widget: Callable[..., Any]) -> None:
    widget = await make_widget()

    socket, ready = await ready_socket(widget, visitor_id="bad")

    assert ready["visitor_id"].startswith("v_")
    assert ready["visitor_id"] != "bad"
    await socket.disconnect()


async def test_foreign_origins_are_rejected_before_accept(make_widget: Callable[..., Any]) -> None:
    widget = await make_widget()

    _, connected, code = await open_socket(widget.site_key, origin="https://evil.example")

    assert not connected
    assert code == CloseCode.FORBIDDEN


@pytest.mark.parametrize("disabled", [False, True])
async def test_unknown_or_disabled_keys_close_with_4404(
    make_widget: Callable[..., Any], disabled: bool
) -> None:
    widget = await make_widget(is_enabled=not disabled)
    key = widget.site_key if disabled else "hlp_pk_does_not_exist"

    socket, connected, _ = await open_socket(key)

    assert connected
    assert (await socket.receive_json_from())["code"] == "invalid_site_key"
    assert (await socket.receive_output())["code"] == CloseCode.NOT_FOUND


async def test_too_many_connections_close_with_4429(make_widget: Callable[..., Any], settings: Any) -> None:
    settings.WIDGET_CONNECTIONS_PER_MINUTE = 1
    widget = await make_widget()
    first, _ = await ready_socket(widget)

    second, connected, _ = await open_socket(widget.site_key)

    assert connected
    error = await second.receive_json_from()
    assert error["code"] == "throttled"
    assert error["details"]["retry_after"] > 0
    assert (await second.receive_output())["code"] == CloseCode.RATE_LIMITED
    await first.disconnect()


# Questions


async def test_questions_stream_the_pipeline_frames(
    make_widget: Callable[..., Any], pipeline: list[Any]
) -> None:
    widget = await make_widget()
    socket, ready = await ready_socket(widget, ip="203.0.113.50")

    await socket.send_json_to(
        {
            "type": "chat.message",
            "client_message_id": "c-1",
            "conversation_id": None,
            "content": "  How long do refunds take?  ",
            "page_url": "https://shop.example.com/help",
        }
    )
    frames = [await socket.receive_json_from() for _ in range(4)]

    assert [frame["type"] for frame in frames] == [
        "message.start",
        "message.delta",
        "message.citations",
        "message.done",
    ]
    assert frames[0]["client_message_id"] == "c-1"
    request = pipeline[0]
    assert request.organization_id == widget.organization_id
    assert request.channel == "widget"
    assert request.content == "How long do refunds take?"
    assert request.conversation_id is None
    assert request.user_id is None
    assert request.visitor.visitor_id == ready["visitor_id"]
    assert request.visitor.origin == SHOP
    assert request.visitor.page_url == "https://shop.example.com/help"
    assert request.visitor.user_agent == "pytest-agent"
    assert request.visitor.ip_hash and "203.0.113.50" not in request.visitor.ip_hash
    await socket.disconnect()


async def test_odd_page_urls_are_dropped_not_refused(
    make_widget: Callable[..., Any], pipeline: list[Any]
) -> None:
    widget = await make_widget()
    socket, _ = await ready_socket(widget)

    await socket.send_json_to(
        {
            "type": "chat.message",
            "client_message_id": "c-1",
            "content": "Hi",
            "page_url": "javascript:alert(1)",
        }
    )
    for _ in range(4):
        await socket.receive_json_from()

    assert pipeline[0].visitor.page_url == ""
    await socket.disconnect()


@pytest.mark.parametrize(
    ("frame", "field"),
    [
        ({"client_message_id": "c-1", "content": "   "}, "content"),
        ({"client_message_id": "c-1", "content": "x" * 2001}, "content"),
        ({"content": "Hello"}, "client_message_id"),
        ({"client_message_id": "c-1", "content": "Hi", "conversation_id": "nope"}, "conversation_id"),
    ],
)
async def test_invalid_questions_get_a_validation_error(
    make_widget: Callable[..., Any], pipeline: list[Any], frame: dict[str, Any], field: str
) -> None:
    widget = await make_widget()
    socket, _ = await ready_socket(widget)

    await socket.send_json_to({"type": "chat.message", **frame})
    error = await socket.receive_json_from()

    assert error["code"] == "validation_error"
    assert field in error["details"]
    assert error.get("client_message_id") == frame.get("client_message_id")
    assert pipeline == []
    await socket.disconnect()


async def test_messages_are_rate_limited_per_ip(
    make_widget: Callable[..., Any], pipeline: list[Any], settings: Any
) -> None:
    settings.WIDGET_MESSAGES_PER_MINUTE = 1
    widget = await make_widget()
    socket, _ = await ready_socket(widget)

    await socket.send_json_to({"type": "chat.message", "client_message_id": "c-1", "content": "One"})
    for _ in range(4):
        await socket.receive_json_from()
    await socket.send_json_to({"type": "chat.message", "client_message_id": "c-2", "content": "Two"})
    error = await socket.receive_json_from()

    assert error["code"] == "throttled"
    assert error["client_message_id"] == "c-2"
    assert error["details"]["retry_after"] > 0
    assert len(pipeline) == 1
    await socket.disconnect()


async def test_one_answer_at_a_time_and_cancel(
    make_widget: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    stop = asyncio.Event()
    cancelled: list[str] = []

    async def slow_pipeline(request: Any) -> AsyncIterator[dict[str, Any]]:
        yield {"type": "message.start", "client_message_id": request.client_message_id, "message_id": "m1"}
        while not stop.is_set():
            yield {"type": "message.delta", "message_id": "m1", "delta": "..."}
            await asyncio.sleep(0.01)
        yield {"type": "message.done", "message_id": "m1", "status": "truncated"}

    def cancel_answer(message_id: str) -> bool:
        cancelled.append(message_id)
        stop.set()
        return True

    monkeypatch.setattr(assistant_services, "stream_answer", slow_pipeline)
    monkeypatch.setattr(assistant_services, "cancel_answer", cancel_answer)
    widget = await make_widget()
    socket, _ = await ready_socket(widget)

    await socket.send_json_to({"type": "chat.message", "client_message_id": "c-1", "content": "First"})
    assert (await socket.receive_json_from())["type"] == "message.start"
    await socket.send_json_to({"type": "chat.message", "client_message_id": "c-2", "content": "Second"})
    await socket.send_json_to({"type": "chat.cancel", "message_id": "m1"})
    frames: list[dict[str, Any]] = []
    while not frames or frames[-1]["type"] != "message.done":
        frames.append(await socket.receive_json_from())

    busy = [frame for frame in frames if frame["type"] == "error"]
    assert [(frame["code"], frame["client_message_id"]) for frame in busy] == [("busy", "c-2")]
    assert cancelled == ["m1"]
    assert frames[-1] == {"type": "message.done", "message_id": "m1", "status": "truncated"}
    await socket.disconnect()


async def test_the_real_pipeline_answers_honestly_without_documents(make_widget: Callable[..., Any]) -> None:
    """Contract check across both backend owners: the widget socket, the real
    stream_answer and billing metering, with no documents to answer from."""
    widget = await make_widget()
    socket, ready = await ready_socket(widget)

    await socket.send_json_to(
        {"type": "chat.message", "client_message_id": "c-1", "content": "Do you ship to Mars?"}
    )
    frames: list[dict[str, Any]] = []
    while not frames or frames[-1]["type"] not in ("message.done", "error"):
        frames.append(await socket.receive_json_from(timeout=10))

    assert [frame["type"] for frame in frames[:1] + frames[-2:]] == [
        "message.start",
        "message.citations",
        "message.done",
    ]
    done = frames[-1]
    assert (done["answer_type"], done["offer_handoff"]) == ("not_found", True)
    assert frames[-2]["citations"] == []

    def stored() -> tuple[str, str, int]:
        from assistant.models import Conversation
        from billing.services import messages_used

        conversation = Conversation.objects.get(pk=done["conversation_id"])
        return conversation.channel, conversation.visitor_id, messages_used(widget.organization_id)

    assert await database_sync_to_async(stored)() == ("widget", ready["visitor_id"], 1)
    await socket.disconnect()


async def test_a_rotated_key_stops_working_on_the_next_frame(
    make_widget: Callable[..., Any], pipeline: list[Any]
) -> None:
    widget = await make_widget()
    socket, _ = await ready_socket(widget)

    await database_sync_to_async(services.rotate_site_key)(widget)
    await socket.send_json_to({"type": "chat.message", "client_message_id": "c-1", "content": "Hi"})

    assert (await socket.receive_json_from())["code"] == "invalid_site_key"
    assert (await socket.receive_output())["code"] == CloseCode.NOT_FOUND
    assert pipeline == []


# Resume, feedback and handoff


async def test_resume_returns_history_or_not_found(
    make_widget: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    known = "11111111-1111-1111-1111-111111111111"
    seen: list[dict[str, Any]] = []

    async def conversation_history(**kwargs: Any) -> dict[str, Any] | None:
        seen.append(kwargs)
        if str(kwargs["conversation_id"]) != known:
            return None
        return {"type": "conversation.history", "conversation_id": known, "status": "open", "messages": []}

    monkeypatch.setattr(assistant_services, "conversation_history", conversation_history)
    widget = await make_widget()
    socket, ready = await ready_socket(widget)

    await socket.send_json_to({"type": "conversation.resume", "conversation_id": known})
    history = await socket.receive_json_from()
    await socket.send_json_to(
        {"type": "conversation.resume", "conversation_id": "22222222-2222-2222-2222-222222222222"}
    )
    missing = await socket.receive_json_from()

    assert history["type"] == "conversation.history"
    assert missing["code"] == "not_found"
    assert seen[0]["visitor_id"] == ready["visitor_id"]
    assert seen[0]["organization_id"] == widget.organization_id
    await socket.disconnect()


async def test_feedback_and_handoff_reach_the_assistant_services(
    make_widget: Callable[..., Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    async def record_feedback(**kwargs: Any) -> dict[str, Any]:
        return {"type": "feedback.ok", "message_id": str(kwargs["message_id"]), "rating": kwargs["rating"]}

    async def create_handoff_ticket(**kwargs: Any) -> dict[str, Any]:
        if kwargs["email"] == "blocked@example.com":
            raise exceptions.NotFound("We could not find that conversation.")
        return {"type": "handoff.created", "ticket": {"id": "t1", "status": "open"}}

    monkeypatch.setattr(assistant_services, "record_feedback", record_feedback)
    monkeypatch.setattr(assistant_services, "create_handoff_ticket", create_handoff_ticket)
    widget = await make_widget()
    socket, _ = await ready_socket(widget)
    message_id = "33333333-3333-3333-3333-333333333333"
    conversation_id = "44444444-4444-4444-4444-444444444444"

    await socket.send_json_to(
        {"type": "feedback", "message_id": message_id, "rating": -1, "comment": "Wrong"}
    )
    feedback = await socket.receive_json_from()
    await socket.send_json_to({"type": "feedback", "message_id": message_id, "rating": 5})
    bad_rating = await socket.receive_json_from()
    await socket.send_json_to(
        {
            "type": "handoff.request",
            "conversation_id": conversation_id,
            "email": "jo@example.net",
            "name": "Jo",
        }
    )
    ticket = await socket.receive_json_from()
    await socket.send_json_to(
        {"type": "handoff.request", "conversation_id": conversation_id, "email": "nope"}
    )
    bad_email = await socket.receive_json_from()
    await socket.send_json_to(
        {"type": "handoff.request", "conversation_id": conversation_id, "email": "blocked@example.com"}
    )
    not_found = await socket.receive_json_from()
    await socket.send_json_to({"type": "subscribe"})
    unknown = await socket.receive_json_from()

    assert feedback == {"type": "feedback.ok", "message_id": message_id, "rating": -1}
    assert bad_rating["code"] == "validation_error"
    assert ticket["type"] == "handoff.created"
    assert "email" in bad_email["details"]
    assert not_found["code"] == "not_found"
    assert unknown["code"] == "unknown_type"
    await socket.disconnect()
