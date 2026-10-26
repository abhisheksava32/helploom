"""REST routes for assistant (conversations/, messages/, tickets/, assistant/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "assistant"

urlpatterns = [
    path("conversations/", views.ConversationListView.as_view(), name="conversation-list"),
    path("conversations/<uuid:pk>/", views.ConversationDetailView.as_view(), name="conversation-detail"),
    path("messages/<uuid:pk>/feedback/", views.MessageFeedbackView.as_view(), name="message-feedback"),
    path("tickets/", views.TicketListView.as_view(), name="ticket-list"),
    path("tickets/<uuid:pk>/", views.TicketDetailView.as_view(), name="ticket-detail"),
    path("assistant/providers/", views.ProviderStatusView.as_view(), name="providers"),
    path("assistant/search/", views.SearchView.as_view(), name="search"),
]
