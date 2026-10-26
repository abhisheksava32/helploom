"""Report endpoints (docs/API.md, section 12). All need the agent role and take
date_from, date_to and channel."""

from __future__ import annotations

from typing import Any

from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.tenancy import OrganizationScopedMixin

from . import services
from .serializers import ReportRangeSerializer, TopListSerializer, UnansweredQuestionSerializer


def _params(
    request: Request, serializer_class: type[ReportRangeSerializer] = ReportRangeSerializer
) -> dict[str, Any]:
    serializer = serializer_class(data=request.query_params)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class ReportView(OrganizationScopedMixin, APIView):
    read_role = "agent"


class OverviewView(ReportView):
    def get(self, request: Request) -> Response:
        return Response(services.overview(self.organization, _params(request)["report"]))


class ConversationsPerDayView(ReportView):
    def get(self, request: Request) -> Response:
        return Response(services.conversations_per_day(self.organization, _params(request)["report"]))


class TopQuestionsView(ReportView):
    def get(self, request: Request) -> Response:
        params = _params(request, TopListSerializer)
        return Response(
            {"results": services.top_questions(self.organization, params["report"], params["limit"])}
        )


class TopDocumentsView(ReportView):
    def get(self, request: Request) -> Response:
        params = _params(request, TopListSerializer)
        return Response(
            {"results": services.top_documents(self.organization, params["report"], params["limit"])}
        )


class UnansweredView(OrganizationScopedMixin, generics.ListAPIView):
    serializer_class = UnansweredQuestionSerializer
    read_role = "agent"

    def get_queryset(self) -> Any:
        return services.unanswered_questions(self.organization, _params(self.request)["report"])


class CostsView(ReportView):
    def get(self, request: Request) -> Response:
        return Response(services.costs(self.organization, _params(request)["report"]))
