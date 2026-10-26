"""Auth, current user, invitation and organisation endpoints (docs/API.md, sections 4
to 6). Each view validates input, calls one function in accounts.services and shapes
the result; the refresh cookie is handled here because it is an HTTP concern.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.db.models import Case, F, IntegerField, QuerySet, Value, When
from rest_framework import exceptions, generics, status
from rest_framework.filters import SearchFilter
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.authentication import JWTAuthentication

from core.authentication import PublicEndpointAuthentication
from core.filters import AliasOrderingFilter
from core.permissions import RequiresCsrfHeader
from core.tenancy import OrganizationScopedMixin

from . import serializers as s
from . import services
from .cookies import clear_refresh_cookie, read_refresh_cookie, set_refresh_cookie
from .models import Invitation, InvitationStatus, Membership, Role, User


def _session_response(
    user: User, pair: services.TokenPair, status_code: int = status.HTTP_200_OK
) -> Response:
    response = Response(s.auth_payload(user, pair.access), status=status_code)
    set_refresh_cookie(response, pair.refresh)
    return response


class PublicAuthView(APIView):
    """Public endpoints that may answer 401 and are throttled per IP as "auth"."""

    authentication_classes = [PublicEndpointAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = "auth"


# Auth


class SignupView(PublicAuthView):
    def post(self, request: Request) -> Response:
        serializer = s.SignupSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        membership = services.signup(**serializer.validated_data)
        return _session_response(
            membership.user, services.issue_tokens(membership.user), status.HTTP_201_CREATED
        )


class LoginView(PublicAuthView):
    def post(self, request: Request) -> Response:
        serializer = s.LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = services.authenticate_credentials(**serializer.validated_data)
        return _session_response(user, services.issue_tokens(user))


class RefreshView(PublicAuthView):
    permission_classes = [RequiresCsrfHeader]

    def post(self, request: Request) -> Response:
        pair = services.rotate_refresh_token(read_refresh_cookie(request))
        response = Response({"access": pair.access})
        set_refresh_cookie(response, pair.refresh)
        return response

    def handle_exception(self, exc: Exception) -> Response:
        response = super().handle_exception(exc)
        if response.status_code == status.HTTP_401_UNAUTHORIZED:
            # A dead cookie is useless; clearing it stops the client retrying with it.
            clear_refresh_cookie(response)
        return response


class LogoutView(PublicAuthView):
    permission_classes = [RequiresCsrfHeader]
    throttle_scope = None  # type: ignore[assignment]

    def post(self, request: Request) -> Response:
        services.revoke_refresh_token(read_refresh_cookie(request))
        response = Response(status=status.HTTP_204_NO_CONTENT)
        clear_refresh_cookie(response)
        return response


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        return Response(s.account_payload(request.user))  # type: ignore[arg-type]

    def patch(self, request: Request) -> Response:
        serializer = s.ProfileUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        user = services.update_profile(request.user, **serializer.validated_data)  # type: ignore[arg-type]
        return Response(s.account_payload(user))


class PasswordView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "auth"

    def post(self, request: Request) -> Response:
        serializer = s.PasswordChangeSerializer(data=request.data, context={"user": request.user})
        serializer.is_valid(raise_exception=True)
        pair = services.change_password(request.user, new_password=serializer.validated_data["new_password"])  # type: ignore[arg-type]
        # Every refresh token was just revoked; this one keeps the caller signed in.
        response = Response(status=status.HTTP_204_NO_CONTENT)
        set_refresh_cookie(response, pair.refresh)
        return response


# Invitations (public side)


class PublicInvitationView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    def get(self, request: Request, token: str) -> Response:
        invitation = services.get_invitation_by_token(token)
        return Response(s.PublicInvitationSerializer(invitation).data)


class AcceptInvitationView(APIView):
    """Signed in mode when a valid bearer token is sent, new account mode otherwise."""

    authentication_classes = [JWTAuthentication]
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    def post(self, request: Request, token: str) -> Response:
        if request.user.is_authenticated:
            membership = services.accept_invitation(raw_token=token, user=request.user)
        else:
            serializer = s.AcceptInvitationSerializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            membership = services.accept_invitation(raw_token=token, user=None, **serializer.validated_data)
        user = membership.user
        return _session_response(user, services.issue_tokens(user))


# Organization


class OrganizationView(OrganizationScopedMixin, APIView):
    read_role = "agent"
    write_role = "admin"

    def get(self, request: Request) -> Response:
        return Response(s.OrganizationSerializer(self.membership).data)

    def patch(self, request: Request) -> Response:
        serializer = s.OrganizationUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        membership = self.membership
        services.update_organization(membership.organization, **serializer.validated_data)
        return Response(s.OrganizationSerializer(membership).data)


ROLE_ORDER = Case(
    When(role=Role.OWNER, then=Value(1)),
    When(role=Role.ADMIN, then=Value(2)),
    default=Value(3),
    output_field=IntegerField(),
)


class MemberListView(OrganizationScopedMixin, generics.ListAPIView):
    queryset = Membership.objects.all()
    serializer_class = s.MemberSerializer
    read_role = "agent"
    filter_backends = [SearchFilter, AliasOrderingFilter]
    search_fields = ["user__email", "user__full_name"]
    ordering_fields = ["created_at", "email", "role"]
    # ?ordering=role lists owners first, then admins, then agents.
    ordering_aliases = {"email": "member_email", "role": "role_rank"}
    ordering = ["created_at"]

    def get_queryset(self) -> QuerySet[Membership]:
        queryset = (
            super()
            .get_queryset()
            .select_related("user")
            .annotate(member_email=F("user__email"), role_rank=ROLE_ORDER)
        )
        role = self.request.query_params.get("role")
        if role:
            if role not in Role.values:
                raise exceptions.ValidationError({"role": [f"Choose one of: {', '.join(Role.values)}."]})
            queryset = queryset.filter(role=role)
        return queryset


class MemberDetailView(OrganizationScopedMixin, generics.GenericAPIView):
    queryset = Membership.objects.select_related("user")
    serializer_class = s.MemberSerializer

    def required_role(self, request: Request) -> str:
        # Changing roles is owner only. Removal is allowed to everyone at this layer
        # because members may leave; the service applies the finer rules.
        if request.method == "PATCH":
            return "owner"
        return "agent"

    def patch(self, request: Request, pk: str) -> Response:
        member = self.get_object()
        serializer = s.MemberRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        member = services.change_member_role(member=member, role=serializer.validated_data["role"])
        return Response(s.MemberSerializer(member).data)

    def delete(self, request: Request, pk: str) -> Response:
        services.remove_member(actor=self.membership, member=self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)


class InvitationListView(OrganizationScopedMixin, generics.ListCreateAPIView):
    queryset = Invitation.objects.select_related("invited_by")
    serializer_class = s.InvitationSerializer
    read_role = "admin"
    write_role = "admin"
    filter_backends: list[Any] = []

    def get_queryset(self) -> QuerySet[Invitation]:
        queryset = super().get_queryset().order_by("-created_at")
        status_filter = self.request.query_params.get("status")
        if status_filter:
            if status_filter not in InvitationStatus.values:
                raise exceptions.ValidationError(
                    {"status": [f"Choose one of: {', '.join(InvitationStatus.values)}."]}
                )
            queryset = queryset.filter(services.invitation_status_filter(status_filter))
        return queryset

    def create(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = s.InvitationCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        issued = services.invite(
            organization=self.organization, actor=self.membership, **serializer.validated_data
        )
        return Response(_invitation_data(issued), status=status.HTTP_201_CREATED)


def _invitation_data(issued: services.IssuedInvitation) -> Any:
    # Without email in local demos the admin needs the link; never outside DEBUG.
    context = {"invite_url": issued.url if settings.DEBUG else None}
    return s.InvitationSerializer(issued.invitation, context=context).data


class InvitationResendView(OrganizationScopedMixin, generics.GenericAPIView):
    queryset = Invitation.objects.select_related("invited_by")
    write_role = "admin"

    def post(self, request: Request, pk: str) -> Response:
        issued = services.resend_invitation(self.get_object())
        return Response(_invitation_data(issued))


class InvitationDetailView(OrganizationScopedMixin, generics.GenericAPIView):
    queryset = Invitation.objects.all()
    write_role = "admin"

    def delete(self, request: Request, pk: str) -> Response:
        services.revoke_invitation(self.get_object())
        return Response(status=status.HTTP_204_NO_CONTENT)
