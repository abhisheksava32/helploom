"""Push events to everyone watching an organisation's dashboard.

Dashboard sockets join the group org.<organization_id>. Any code (views, ingestion
threads, Celery tasks, async consumers) can broadcast an event dict; the dashboard
consumer forwards it unchanged, so the event shape is the wire shape in docs/API.md.

The in-memory channel layer belongs to the server's event loop and is not thread safe,
so events raised in worker threads are handed to that loop. With Redis the layer is
shared across processes and any thread may send directly.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from uuid import UUID

from asgiref.sync import async_to_sync
from channels.layers import InMemoryChannelLayer, get_channel_layer

logger = logging.getLogger(__name__)

_server_loop: asyncio.AbstractEventLoop | None = None


def org_group(organization_id: UUID | str) -> str:
    return f"org.{organization_id}"


def remember_server_loop() -> None:
    """Called by consumers on connect so worker threads know which loop owns the layer."""
    global _server_loop
    _server_loop = asyncio.get_running_loop()


def _message(event: dict[str, Any]) -> dict[str, Any]:
    return {"type": "org.event", "event": event}


async def abroadcast_org_event(organization_id: UUID | str, event: dict[str, Any]) -> None:
    layer = get_channel_layer()
    if layer is None:
        return
    await layer.group_send(org_group(organization_id), _message(event))


def broadcast_org_event(organization_id: UUID | str, event: dict[str, Any]) -> None:
    """Fire and forget from synchronous code. Never raises: a missed live update must not
    fail the work that produced it."""
    layer = get_channel_layer()
    if layer is None:
        return
    group = org_group(organization_id)
    try:
        if isinstance(layer, InMemoryChannelLayer):
            loop = _server_loop
            if loop is None or loop.is_closed() or not loop.is_running():
                return  # no socket has connected in this process, nobody is listening
            asyncio.run_coroutine_threadsafe(layer.group_send(group, _message(event)), loop)
            return
        async_to_sync(layer.group_send)(group, _message(event))
    except Exception:
        logger.warning("Could not broadcast %s to %s", event.get("type"), group, exc_info=True)
