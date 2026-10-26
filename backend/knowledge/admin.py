from django.contrib import admin

from .models import Chunk, Collection, Document, IngestionJob


@admin.register(Collection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ["name", "organization", "created_at"]


class IngestionJobInline(admin.TabularInline):
    model = IngestionJob
    extra = 0
    fields = ("trigger", "status", "embedder", "chunk_count", "duration_ms", "error_message", "created_at")
    readonly_fields = fields
    can_delete = False


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "status", "chunk_count", "embedder", "created_at"]
    list_filter = ["status"]
    search_fields = ["title", "original_filename"]
    exclude = ["extracted_text"]
    inlines = [IngestionJobInline]


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ["document", "ordinal", "location", "token_count", "embedder"]
    exclude = ["embedding"]
    raw_id_fields = ["document"]


@admin.register(IngestionJob)
class IngestionJobAdmin(admin.ModelAdmin):
    list_display = ["document", "trigger", "status", "embedder", "chunk_count", "duration_ms", "created_at"]
    list_filter = ["status", "trigger"]
    raw_id_fields = ["document"]
