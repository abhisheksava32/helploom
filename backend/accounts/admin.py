from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import Invitation, Membership, Organization, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ["email"]
    list_display = ["email", "full_name", "is_active", "is_staff", "date_joined"]
    search_fields = ["email", "full_name"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Profile", {"fields": ("full_name",)}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
        ("Dates", {"fields": ("last_login", "date_joined")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)


class MembershipInline(admin.TabularInline):
    model = Membership
    extra = 0
    raw_id_fields = ["user"]


@admin.register(Organization)
class OrganizationAdmin(admin.ModelAdmin):
    list_display = ["name", "slug", "assistant_tone", "created_at"]
    search_fields = ["name", "slug"]
    inlines = [MembershipInline]


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = ["email", "organization", "role", "expires_at", "accepted_at", "revoked_at"]
    search_fields = ["email"]
    exclude = ["token_hash"]
