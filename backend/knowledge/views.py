"""Document and collection endpoints. Owner: backend-ai. Contract: docs/API.md,
section "Documents and collections".

Views stay thin: OrganizationScopedMixin resolves the organisation and role, a
serializer validates input, one knowledge.services call does the work. Detail views
look objects up through get_queryset(), which the mixin filters by organisation, so
another tenant's id is a plain 404.
"""

from __future__ import annotations

from typing import Any

from rest_framework import generics, status
from rest_framework.request import Request
from rest_framework.response import Response

from core.tenancy import OrganizationScopedMixin

from . import services
from .models import Collection, Document
from .serializers import (
    ChunkSerializer,
    CollectionListQuerySerializer,
    CollectionSerializer,
    CollectionWriteSerializer,
    DocumentListQuerySerializer,
    DocumentSerializer,
    DocumentTextSerializer,
    DocumentUpdateSerializer,
    DocumentUploadSerializer,
    TagCountSerializer,
)


def _validated(serializer_class: type[Any], data: Any) -> dict[str, Any]:
    serializer = serializer_class(data=data)
    serializer.is_valid(raise_exception=True)
    return dict(serializer.validated_data)


class DocumentListView(OrganizationScopedMixin, generics.GenericAPIView):
    serializer_class = DocumentSerializer

    def get_throttles(self) -> list[Any]:
        # Only uploads are expensive; listing stays on the normal user rate.
        self.throttle_scope = "upload" if self.request.method == "POST" else ""
        return super().get_throttles()

    def get(self, request: Request) -> Response:
        filters = _validated(DocumentListQuerySerializer, request.query_params)
        queryset = services.document_queryset(self.organization, **filters)
        page = self.paginate_queryset(queryset)
        return self.get_paginated_response(DocumentSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        data = _validated(DocumentUploadSerializer, request.data)
        result = services.accept_uploads(
            self.organization,
            data["files"],
            uploaded_by=self.membership.user,
            collection_id=data.get("collection_id"),
            tags=data.get("tags", []),
        )
        body = {
            "documents": DocumentSerializer(result.documents, many=True).data,
            "rejected": result.rejected,
        }
        return Response(body, status=status.HTTP_201_CREATED)


class DocumentTagsView(OrganizationScopedMixin, generics.GenericAPIView):
    def get(self, request: Request) -> Response:
        return Response(
            {"results": TagCountSerializer(services.tag_counts(self.organization), many=True).data}
        )


class DocumentObjectView(OrganizationScopedMixin, generics.GenericAPIView):
    queryset = Document.objects.select_related("collection", "uploaded_by", "organization")


class DocumentDetailView(DocumentObjectView):
    serializer_class = DocumentSerializer

    def get(self, request: Request, pk: str) -> Response:
        return Response(DocumentSerializer(self.get_object()).data)

    def patch(self, request: Request, pk: str) -> Response:
        document = self.get_object()
        data = _validated(DocumentUpdateSerializer, request.data)
        document = services.update_document(document, **data)
        return Response(DocumentSerializer(document).data)

    def delete(self, request: Request, pk: str) -> Response:
        services.delete_document(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class DocumentReindexView(DocumentObjectView):
    def post(self, request: Request, pk: str) -> Response:
        document = services.reindex_document(self.get_object())
        return Response(DocumentSerializer(document).data, status=status.HTTP_202_ACCEPTED)


class DocumentTextView(DocumentObjectView):
    def get(self, request: Request, pk: str) -> Response:
        return Response(DocumentTextSerializer(services.document_text(self.get_object())).data)


class DocumentChunksView(DocumentObjectView):
    serializer_class = ChunkSerializer

    def get(self, request: Request, pk: str) -> Response:
        page = self.paginate_queryset(services.document_chunks(self.get_object()))
        return self.get_paginated_response(ChunkSerializer(page, many=True).data)


class CollectionListView(OrganizationScopedMixin, generics.GenericAPIView):
    serializer_class = CollectionSerializer

    def get(self, request: Request) -> Response:
        filters = _validated(CollectionListQuerySerializer, request.query_params)
        page = self.paginate_queryset(services.collection_queryset(self.organization, **filters))
        return self.get_paginated_response(CollectionSerializer(page, many=True).data)

    def post(self, request: Request) -> Response:
        data = _validated(CollectionWriteSerializer, request.data)
        collection = services.create_collection(self.organization, **data)
        return Response(CollectionSerializer(collection).data, status=status.HTTP_201_CREATED)


class CollectionDetailView(OrganizationScopedMixin, generics.GenericAPIView):
    queryset = Collection.objects.select_related("organization")
    serializer_class = CollectionSerializer

    def get(self, request: Request, pk: str) -> Response:
        collection = services.collection_queryset(self.organization).get(pk=self.get_object().pk)
        return Response(CollectionSerializer(collection).data)

    def patch(self, request: Request, pk: str) -> Response:
        collection = self.get_object()
        serializer = CollectionWriteSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        collection = services.update_collection(collection, **serializer.validated_data)
        return Response(CollectionSerializer(collection).data)

    def delete(self, request: Request, pk: str) -> Response:
        services.delete_collection(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
