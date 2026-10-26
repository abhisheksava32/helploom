"""REST routes for widget (/api/v1/widget/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "widget"

urlpatterns = [
    path("config/", views.WidgetConfigView.as_view(), name="config"),
    path("config/rotate-key/", views.RotateSiteKeyView.as_view(), name="rotate-key"),
    path("public/config/", views.PublicWidgetConfigView.as_view(), name="public-config"),
]
