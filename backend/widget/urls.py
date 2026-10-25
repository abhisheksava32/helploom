"""REST routes for widget (/api/v1/widget/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "widget"

urlpatterns: list[URLPattern | URLResolver] = []
