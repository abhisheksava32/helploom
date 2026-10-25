"""REST routes for billing (/api/v1/billing/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "billing"

urlpatterns: list[URLPattern | URLResolver] = []
