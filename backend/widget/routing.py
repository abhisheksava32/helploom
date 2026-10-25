from django.urls import path

from .consumers import WidgetConsumer

websocket_urlpatterns = [
    path("ws/widget/", WidgetConsumer.as_asgi()),
]
