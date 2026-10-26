"""Conversation, message feedback, ticket, provider status and retrieval preview
endpoints. Owner: backend-ai. Contract: docs/API.md, sections "Conversations,
feedback and tickets" and "Assistant".

Questions themselves are asked over ws/chat/ and ws/widget/, not REST. Every view
here needs the agent role, including the writes: triaging conversations and tickets
is the agent's job.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet
from rest_framework import generics
from rest_framework.request import Request
from rest_framework.response import Response

from core.tenancy import OrganizationScopedMixin

from . import services
from .models import Conversation, HandoffTicket, Message
from .serializers import (
    ConversationDetailSerializer,
    ConversationListQuerySerializer,
    ConversationSummarySerializer,
    ConversationUpdateSerializer,
    FeedbackSerializer,
    MessageSerializer,
    SearchRequestSerializer,
    SearchResponseSerializer,
    TicketListQuerySerializer,
    TicketSerializer,
    TicketUpdateSerializer,
)


def _validated(serializer_class: type[Any], data: Any) -> dict[str, Any]:
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class AgentScopedView(OrganizationScopedMixin, generics.GenericAPIView):
    read_role = "agent"
    write_role = "agent"


class ConversationListView(AgentScopedView):
    serializer_class = ConversationSummarySerializer

    def get(self, request: Request) -> Response:
        filters = _validated(ConversationListQuerySerializer, request.query_params)
        page = self.paginate_queryset(services.conversation_queryset(self.organization, **filters))
        return self.get_paginated_response(ConversationSummarySerializer(page, many=True).data)


class ConversationDetailView(AgentScopedView):
    serializer_class = ConversationDetailSerializer

    def get_queryset(self) -> QuerySet[Conversation]:
        return services.conversation_detail_queryset(self.organization)

    def get(self, request: Request, pk: str) -> Response:
        return Response(ConversationDetailSerializer(self.get_object()).data)

    def patch(self, request: Request, pk: str) -> Response:
        data = _validated(ConversationUpdateSerializer, request.data)
        conversation = services.update_conversation(self.get_object(), **data)
        return Response(ConversationSummarySerializer(conversation).data)


class MessageFeedbackView(AgentScopedView):
    queryset = Message.objects.select_related("conversation")
    serializer_class = MessageSerializer

    def post(self, request: Request, pk: str) -> Response:
        data = _validated(FeedbackSerializer, request.data)
        message = services.rate_message(
            self.get_object(), rating=data["rating"], comment=data.get("comment", "")
        )
        return Response(MessageSerializer(message).data)


class TicketListView(AgentScopedView):
    serializer_class = TicketSerializer

    def get(self, request: Request) -> Response:
        filters = _validated(TicketListQuerySerializer, request.query_params)
        queryset = services.ticket_queryset(self.organization, user=self.membership.user, **filters)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(TicketSerializer(page, many=True).data)


class TicketDetailView(AgentScopedView):
    queryset = HandoffTicket.objects.select_related("assigned_to", "conversation")
    serializer_class = TicketSerializer

    def get(self, request: Request, pk: str) -> Response:
        return Response(TicketSerializer(self.get_object()).data)

    def patch(self, request: Request, pk: str) -> Response:
        serializer = TicketUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        ticket = services.update_ticket(self.get_object(), **serializer.validated_data)
        return Response(TicketSerializer(ticket).data)


class ProviderStatusView(AgentScopedView):
    def get(self, request: Request) -> Response:
        return Response(services.provider_report(self.organization))


class SearchView(AgentScopedView):
    serializer_class = SearchRequestSerializer

    def post(self, request: Request) -> Response:
        data = _validated(SearchRequestSerializer, request.data)
        result = services.search_preview(self.organization, query=data["query"], top_k=data.get("top_k"))
        return Response(SearchResponseSerializer(result).data)
