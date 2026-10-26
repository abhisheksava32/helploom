"""REST routes for knowledge (documents/, collections/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "knowledge"

urlpatterns = [
    path("documents/", views.DocumentListView.as_view(), name="document-list"),
    path("documents/tags/", views.DocumentTagsView.as_view(), name="document-tags"),
    path("documents/<uuid:pk>/", views.DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<uuid:pk>/reindex/", views.DocumentReindexView.as_view(), name="document-reindex"),
    path("documents/<uuid:pk>/text/", views.DocumentTextView.as_view(), name="document-text"),
    path("documents/<uuid:pk>/chunks/", views.DocumentChunksView.as_view(), name="document-chunks"),
    path("collections/", views.CollectionListView.as_view(), name="collection-list"),
    path("collections/<uuid:pk>/", views.CollectionDetailView.as_view(), name="collection-detail"),
]
