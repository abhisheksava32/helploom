"""Role based access for dashboard endpoints.

Roles are ordered: owner > admin > agent. A view states the lowest role it accepts and
HasOrganizationRole checks the caller's membership in the request's organisation (see
core.tenancy for how that organisation is chosen).
"""

from __future__ import annotations

from typing import Any

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

    def has_permission(self, request: Any, view: Any) -> bool:
        from core.tenancy import get_request_membership

        membership = get_request_membership(request)
        if membership is None:
            self.message = IsOrganizationMember.message
            self.code = IsOrganizationMember.code
            return False
        required = required_role_for(view, request)
        if has_role(membership.role, required):
            return True
        self.message = f"This action needs the {required} role or higher."
        self.code = "insufficient_role"
        return False
