"""REST routes for analytics (/api/v1/analytics/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "analytics"

urlpatterns: list[URLPattern | URLResolver] = []
