from django.contrib import admin

from .models import Citation, Conversation, HandoffTicket, Message

MESSAGE_FIELDS = ("role", "content", "answer_type", "provider", "model", "latency_ms", "rating")


class MessageInline(admin.TabularInline):
    model = Message
    extra = 0
    fields = MESSAGE_FIELDS
    readonly_fields = MESSAGE_FIELDS


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ["title", "organization", "channel", "status", "message_count", "last_message_at"]
    list_filter = ["channel", "status"]
    inlines = [MessageInline]


@admin.register(Citation)
class CitationAdmin(admin.ModelAdmin):
    list_display = ["message", "marker", "document_title", "location"]


@admin.register(HandoffTicket)
class HandoffTicketAdmin(admin.ModelAdmin):
    list_display = ["requester_email", "organization", "status", "created_at"]
    list_filter = ["status"]
