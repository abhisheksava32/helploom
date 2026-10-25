from django.contrib import admin

from .models import StripeEvent, Subscription, UsageCounter


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["organization", "plan", "status", "provider", "current_period_end"]
    list_filter = ["plan", "status", "provider"]


@admin.register(UsageCounter)
class UsageCounterAdmin(admin.ModelAdmin):
    list_display = ["organization", "period_start", "messages"]


@admin.register(StripeEvent)
class StripeEventAdmin(admin.ModelAdmin):
    list_display = ["event_id", "type", "received_at", "processed_at"]
