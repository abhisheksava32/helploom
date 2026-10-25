"""Public widget socket. Protocol: docs/API.md, "ws/widget/".

Owner: backend-core. The finished consumer checks the site key, the Origin header
against the organisation's allowed origins and a per IP rate limit before accepting,
then forwards the frames of assistant.services.stream_answer.
"""

from __future__ import annotations

from core.consumers import CloseCode, JsonWebsocketConsumer


class WidgetConsumer(JsonWebsocketConsumer):
    async def connect(self) -> None:
        await self.accept()
        await self.send_error("not_implemented", "The widget socket is not wired up yet.")
        await self.close(code=CloseCode.INTERNAL_ERROR)
