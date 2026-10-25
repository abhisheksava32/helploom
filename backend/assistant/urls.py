"""REST routes for assistant (conversations/, messages/, tickets/, assistant/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "assistant"

urlpatterns: list[URLPattern | URLResolver] = []
