"""Multi-tenancy: every dashboard request runs inside exactly one organisation.

The client names the organisation with the X-Organization-Id header. Without it we fall
back to the user's oldest membership, which is what single workspace users have. Views
built on OrganizationScopedMixin get request.organization and request.membership, and
querysets already filtered to that organisation, so forgetting a filter cannot leak
another tenant's rows. Code outside views filters with
Model.objects.for_organization(org).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, cast
from uuid import UUID

from channels.db import database_sync_to_async
from django.conf import settings
from rest_framework import exceptions
from rest_framework.permissions import IsAuthenticated

from core.models import OrganizationQuerySet
from core.permissions import HasOrganizationRole, IsOrganizationMember

if TYPE_CHECKING:
    from rest_framework.permissions import _PermissionClass

    from accounts.models import Membership, Organization, User

_UNSET = object()


def resolve_membership(user: User, organization_id: str | None) -> Membership | None:
    from accounts.models import Membership

    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return None
    memberships = Membership.objects.select_related("organization", "user").filter(user=user)
    if organization_id:
        try:
            org_uuid = UUID(str(organization_id))
        except ValueError:
            return None
        return memberships.filter(organization_id=org_uuid).first()
    return memberships.order_by("created_at").first()


aresolve_membership = database_sync_to_async(resolve_membership)


def get_request_membership(request: Any) -> Membership | None:
    """Resolve once per request and cache the result on the request object."""
    cached = getattr(request, "_helploom_membership", _UNSET)
    if cached is not _UNSET:
        return cast("Membership | None", cached)
    membership = resolve_membership(request.user, request.headers.get(settings.ORGANIZATION_HEADER))
    request._helploom_membership = membership
    if membership is not None:
        request.membership = membership
        request.organization = membership.organization
    return membership


class OrganizationScopedMixin:
    """Mix into DRF views before the generic base class.

    read_role applies to GET/HEAD/OPTIONS and write_role to everything else; define
    required_role(request) for per action rules (for example billing changes need
    "owner").
    """

    permission_classes: Sequence[_PermissionClass] = [IsAuthenticated, HasOrganizationRole]
    read_role = "agent"
    write_role = "admin"

    request: Any

    @property
    def membership(self) -> Membership:
        membership = get_request_membership(self.request)
        if membership is None:
            raise exceptions.PermissionDenied(IsOrganizationMember.message, code=IsOrganizationMember.code)
        return membership

    @property
    def organization(self) -> Organization:
        return self.membership.organization

    def get_queryset(self) -> Any:
        queryset = super().get_queryset()  # type: ignore[misc]
        return queryset.filter(organization=self.organization)


__all__ = [
    "OrganizationQuerySet",
    "OrganizationScopedMixin",
    "aresolve_membership",
    "get_request_membership",
    "resolve_membership",
]
