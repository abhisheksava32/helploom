"""Role based access for dashboard endpoints.

Roles are ordered: owner > admin > agent. A view states the lowest role it accepts and
HasOrganizationRole checks the caller's membership in the request's organisation (see
core.tenancy for how that organisation is chosen). Views that need one fixed role for
every method can use IsOrgMember, IsOrgAdmin or IsOrgOwner instead.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from rest_framework import exceptions
from rest_framework.permissions import SAFE_METHODS, BasePermission

ROLE_RANK = {"agent": 1, "admin": 2, "owner": 3}


def has_role(role: str, minimum: str) -> bool:
    return ROLE_RANK.get(role, 0) >= ROLE_RANK[minimum]


def required_role_for(view: Any, request: Any) -> str:
    """The role a view demands for this request.

    Views may define required_role(request) for per action rules; otherwise read_role
    applies to safe methods and write_role to everything else.
    """
    custom = getattr(view, "required_role", None)
    if callable(custom):
        return str(custom(request))
    if request.method in SAFE_METHODS:
        return str(getattr(view, "read_role", "agent"))
    return str(getattr(view, "write_role", "admin"))


class IsOrganizationMember(BasePermission):
    """The caller belongs to the organisation named by the request."""

    message = "You are not a member of this organization."
    code = "not_a_member"

    def has_permission(self, request: Any, view: Any) -> bool:
        from core.tenancy import get_request_membership

        return get_request_membership(request) is not None


class HasOrganizationRole(IsOrganizationMember):
    """Membership plus the minimum role from required_role_for()."""

    def minimum_role(self, request: Any, view: Any) -> str:
        return required_role_for(view, request)

    def has_permission(self, request: Any, view: Any) -> bool:
        from core.tenancy import get_request_membership

        membership = get_request_membership(request)
        if membership is None:
            self.message = IsOrganizationMember.message
            self.code = IsOrganizationMember.code
            return False
        required = self.minimum_role(request, view)
        if has_role(membership.role, required):
            return True
        self.message = f"This action needs the {required} role or higher."
        self.code = "insufficient_role"
        return False


class IsOrgAdmin(HasOrganizationRole):
    """Admin or owner for every method, whatever the view's read and write roles say."""

    fixed_role = "admin"

    def minimum_role(self, request: Any, view: Any) -> str:
        return self.fixed_role


class IsOrgOwner(IsOrgAdmin):
    fixed_role = "owner"


# Short names used across the apps.
IsOrgMember = IsOrganizationMember


class RequiresCsrfHeader(BasePermission):
    """Cookie authenticated endpoints need X-Requested-With: XMLHttpRequest.

    Browsers cannot add a custom header to a cross origin request without a CORS
    preflight, and only the dashboard origin passes it, so a forged form post or
    cross site fetch never carries the header. It raises instead of returning False
    because DRF reports a failed permission on an unauthenticated request as 401, and
    the contract wants 403 csrf_header_missing here.
    """

    message = "This request needs the X-Requested-With: XMLHttpRequest header."
    code = "csrf_header_missing"

    def has_permission(self, request: Any, view: Any) -> bool:
        value = request.headers.get(settings.CSRF_GUARD_HEADER, "")
        if value.strip().lower() != "xmlhttprequest":
            raise exceptions.PermissionDenied(self.message, code=self.code)
        return True
