"""REST routes for knowledge (documents/, collections/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "knowledge"

urlpatterns: list[URLPattern | URLResolver] = []
