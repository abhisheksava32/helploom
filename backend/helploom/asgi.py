"""ASGI entry point: HTTP goes to Django, websockets go to the apps' routing modules.

Origin checks happen per consumer rather than with a global validator, because the
public widget socket accepts each organisation's own allowed origins while the
dashboard sockets accept only the dashboard origin.
"""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helploom.settings")

# Django must be set up before any consumer (and therefore any model) is imported.
django_asgi_app = get_asgi_application()

from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402

from assistant.routing import websocket_urlpatterns as assistant_websockets  # noqa: E402
from core.routing import websocket_urlpatterns as core_websockets  # noqa: E402
from widget.routing import websocket_urlpatterns as widget_websockets  # noqa: E402

websocket_urlpatterns = [
    *core_websockets,
    *assistant_websockets,
    *widget_websockets,
]

application = ProtocolTypeRouter(
    {
        "http": django_asgi_app,
        "websocket": URLRouter(websocket_urlpatterns),
    }
)
