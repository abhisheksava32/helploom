"""REST routes for analytics (/api/v1/analytics/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "analytics"

urlpatterns = [
    path("overview/", views.OverviewView.as_view(), name="overview"),
    path("conversations-per-day/", views.ConversationsPerDayView.as_view(), name="conversations-per-day"),
    path("top-questions/", views.TopQuestionsView.as_view(), name="top-questions"),
    path("top-documents/", views.TopDocumentsView.as_view(), name="top-documents"),
    path("unanswered/", views.UnansweredView.as_view(), name="unanswered"),
    path("costs/", views.CostsView.as_view(), name="costs"),
]
