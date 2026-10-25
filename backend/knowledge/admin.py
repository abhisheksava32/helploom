from django.contrib import admin

from .models import Chunk, Collection, Document


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "created_at"]


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "status", "chunk_count", "embedder", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "original_filename"]
    exclude = ["extracted_text"]


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "ordinal", "location", "token_count", "embedder"]
    exclude = ["embedding"]
    raw_id_fields = ["document"]
