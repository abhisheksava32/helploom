from django.contrib import admin

from .models import WidgetConfig


@admin.register(WidgetConfig)
class WidgetConfigAdmin(admin.ModelAdmin):
    list_display = ["organization", "site_key", "is_enabled", "updated_at"]
