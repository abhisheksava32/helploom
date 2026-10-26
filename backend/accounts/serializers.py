"""Request validation and response shapes for auth, the current user, organisations,
members and invitations. Field names follow docs/API.md ("Shared objects", "Auth",
"Invitations", "Organization"). Every output field is listed explicitly so a column
added later cannot leak through the API.
"""

from __future__ import annotations

from typing import Any

from rest_framework import serializers

from . import services
from .models import Invitation, Role, Tone, User, normalize_email

# Output shapes


class UserRefSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    full_name = serializers.CharField(read_only=True)


class UserSerializer(UserRefSerializer):
    date_joined = serializers.DateTimeField(read_only=True)


class OrganizationSerializer(serializers.Serializer):
    """An organisation as one member sees it, so it is built from that Membership."""

    id = serializers.UUIDField(source="organization.id", read_only=True)
    name = serializers.CharField(source="organization.name", read_only=True)
    slug = serializers.CharField(source="organization.slug", read_only=True)
    assistant_tone = serializers.CharField(source="organization.assistant_tone", read_only=True)
    created_at = serializers.DateTimeField(source="organization.created_at", read_only=True)
    role = serializers.CharField(read_only=True)


def account_payload(user: User) -> dict[str, Any]:
    """The {"user", "organizations"} part shared by AuthResponse and GET /auth/me/."""
    return {
        "user": UserSerializer(user).data,
        "organizations": OrganizationSerializer(services.memberships_for(user), many=True).data,
    }


def auth_payload(user: User, access: str) -> dict[str, Any]:
    return {"access": access, **account_payload(user)}


class MemberSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    user = UserRefSerializer(read_only=True)
    role = serializers.CharField(read_only=True)
    created_at = serializers.DateTimeField(read_only=True)


class InvitationSerializer(serializers.Serializer):
    """invite_url is only known right after create or resend; the view passes it in the
    context (and only while DEBUG is on)."""

    id = serializers.UUIDField(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    invited_by = UserRefSerializer(read_only=True, allow_null=True)
    expires_at = serializers.DateTimeField(read_only=True)
    accepted_at = serializers.DateTimeField(read_only=True, allow_null=True)
    created_at = serializers.DateTimeField(read_only=True)
    invite_url = serializers.SerializerMethodField()

    def get_invite_url(self, invitation: Invitation) -> str | None:
        url = self.context.get("invite_url")
        return str(url) if url else None


class InvitationOrganizationSerializer(serializers.Serializer):
    id = serializers.UUIDField(read_only=True)
    name = serializers.CharField(read_only=True)


class PublicInvitationSerializer(serializers.Serializer):
    organization = InvitationOrganizationSerializer(read_only=True)
    email = serializers.EmailField(read_only=True)
    role = serializers.CharField(read_only=True)
    status = serializers.CharField(read_only=True)
    expires_at = serializers.DateTimeField(read_only=True)
    invited_by_name = serializers.SerializerMethodField()
    account_exists = serializers.SerializerMethodField()

    def get_invited_by_name(self, invitation: Invitation) -> str:
        inviter = invitation.invited_by
        if inviter is None:
            return ""
        return inviter.full_name or inviter.email

    def get_account_exists(self, invitation: Invitation) -> bool:
        return services.account_exists(invitation.email)


# Input validation


class PasswordField(serializers.CharField):
    """Passwords are taken exactly as typed: no trimming, never echoed back."""

    def __init__(self, **kwargs: Any) -> None:
        kwargs.setdefault("write_only", True)
        kwargs.setdefault("trim_whitespace", False)
        kwargs.setdefault("max_length", 128)
        kwargs.setdefault("style", {"input_type": "password"})
        super().__init__(**kwargs)


class SignupSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = PasswordField()
    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    organization_name = serializers.CharField(min_length=2, max_length=150)

    def validate_email(self, value: str) -> str:
        email = normalize_email(value)
        if services.account_exists(email):
            raise serializers.ValidationError(services.EMAIL_TAKEN)
        return email

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        errors = services.password_errors(
            attrs["password"], email=attrs["email"], full_name=attrs.get("full_name", "")
        )
        if errors:
            raise serializers.ValidationError({"password": errors})
        return attrs


class LoginSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    password = PasswordField()


class ProfileUpdateSerializer(serializers.Serializer):
    full_name = serializers.CharField(max_length=150, allow_blank=True, required=False)


class PasswordChangeSerializer(serializers.Serializer):
    current_password = PasswordField()
    new_password = PasswordField()

    def validate_current_password(self, value: str) -> str:
        user: User = self.context["user"]
        if not user.check_password(value):
            raise serializers.ValidationError("Your current password is not correct.")
        return value

    def validate_new_password(self, value: str) -> str:
        user: User = self.context["user"]
        errors = services.password_errors(value, email=user.email, full_name=user.full_name)
        if errors:
            raise serializers.ValidationError(errors)
        return value


class OrganizationUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(min_length=2, max_length=150, required=False)
    assistant_tone = serializers.ChoiceField(choices=Tone.choices, required=False)


class MemberRoleSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=Role.choices)


class InvitationCreateSerializer(serializers.Serializer):
    email = serializers.EmailField(max_length=254)
    role = serializers.ChoiceField(choices=Role.choices, default=Role.AGENT)

    def validate_email(self, value: str) -> str:
        return normalize_email(value)


class AcceptInvitationSerializer(serializers.Serializer):
    """New account mode. Signed in mode sends an empty body and skips this."""

    full_name = serializers.CharField(max_length=150, required=False, allow_blank=True, default="")
    password = PasswordField()
