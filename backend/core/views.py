"""Health check and JSON error pages for API paths."""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest, HttpResponse, JsonResponse
from django.views.defaults import page_not_found
from django.views.defaults import server_error as html_server_error
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core import services
from core.exceptions import error_body
from core.serializers import HealthSerializer


class HealthView(APIView):
    """Liveness plus a database round trip. Used by docker-compose and uptime checks."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes: list[Any] = []

    def get(self, request: Request) -> Response:
        report = services.health_report()
        status_code = 200 if report["status"] == "ok" else 503
        return Response(HealthSerializer(report).data, status=status_code)


def not_found(request: HttpRequest, exception: Exception) -> HttpResponse:
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("not_found", "No endpoint matches this URL."), status=404)
    return page_not_found(request, exception)


def server_error(request: HttpRequest) -> HttpResponse:
    if request.path.startswith("/api/"):
        return JsonResponse(error_body("server_error", "Something went wrong on our side."), status=500)
    return html_server_error(request)
