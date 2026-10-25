"""Platform routes (/api/v1/health/). Contract: docs/API.md."""

from django.urls import path

from .views import HealthView

app_name = "core"

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
]
