"""REST routes for accounts (auth/, organization/, invitations/). Contract: docs/API.md."""

from django.urls import URLPattern, URLResolver

app_name = "accounts"

urlpatterns: list[URLPattern | URLResolver] = []
