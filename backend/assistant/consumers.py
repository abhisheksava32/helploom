"""Dashboard playground chat socket. Protocol: docs/API.md, "ws/chat/".

Owner: backend-ai. The scaffold only authenticates; chat.message handling forwards
the frames of assistant.services.stream_answer once it exists.
"""

from __future__ import annotations

from typing import Any

from core.consumers import AuthenticatedJsonConsumer


class ChatConsumer(AuthenticatedJsonConsumer):
    async def handle_message(self, content: dict[str, Any]) -> None:
        if content["type"] == "chat.message":
            await self.send_error(
                "not_implemented",
                "The answer pipeline is not wired up yet.",
                client_message_id=content.get("client_message_id"),
            )
            return
        await super().handle_message(content)
