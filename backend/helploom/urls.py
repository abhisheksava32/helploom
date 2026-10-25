"""Root URL map. Every REST endpoint lives under /api/v1/ and ends with a slash.

Each app owns its routes in its own urls.py; the prefixes here match docs/API.md.
"""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/v1/", include("core.urls")),
    path("api/v1/", include("accounts.urls")),
    path("api/v1/", include("knowledge.urls")),
    path("api/v1/", include("assistant.urls")),
    path("api/v1/widget/", include("widget.urls")),
    path("api/v1/billing/", include("billing.urls")),
    path("api/v1/analytics/", include("analytics.urls")),
]

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"
