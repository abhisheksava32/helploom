"""Widget settings (dashboard) and the public config endpoint (docs/API.md, section 10)."""

from __future__ import annotations

from typing import Any

from django.utils.cache import patch_vary_headers
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.tenancy import OrganizationScopedMixin

from . import services
from .serializers import (
    PublicWidgetConfigSerializer,
    WidgetSettingsSerializer,
    WidgetSettingsUpdateSerializer,
)


class WidgetConfigView(OrganizationScopedMixin, APIView):
    read_role = "agent"
    write_role = "admin"

    def get(self, request: Request) -> Response:
        return Response(WidgetSettingsSerializer(services.get_widget(self.organization)).data)

    def patch(self, request: Request) -> Response:
        serializer = WidgetSettingsUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        widget = services.update_widget(services.get_widget(self.organization), **serializer.validated_data)
        return Response(WidgetSettingsSerializer(widget).data)


class RotateSiteKeyView(OrganizationScopedMixin, APIView):
    write_role = "admin"

    def post(self, request: Request) -> Response:
        widget = services.rotate_site_key(services.get_widget(self.organization))
        return Response(WidgetSettingsSerializer(widget).data)


class PublicWidgetConfigView(APIView):
    """Called by widget.js on a customer's site, without credentials or custom headers,
    so the browser sends no preflight. The allowed origin is echoed back, never *."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    # Only the widget scope: the general anon rate would cap busy storefronts at 60/min.
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "widget"

    def get(self, request: Request) -> Response:
        origin = request.headers.get("Origin")
        widget = services.resolve_public_widget(request.query_params.get("site_key"), origin)
        response = Response(PublicWidgetConfigSerializer(services.public_config(widget)).data)
        response["Access-Control-Allow-Origin"] = origin or ""
        patch_vary_headers(response, ("Origin",))
        return response
