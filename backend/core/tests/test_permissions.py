"""Fixed role permissions, the CSRF header guard and the 401 preserving public auth."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.test import APIRequestFactory, force_authenticate
from rest_framework.views import APIView

from accounts.models import Membership, Role
from core.authentication import PublicEndpointAuthentication
from core.exceptions import InvalidCredentials
from core.permissions import IsOrgAdmin, IsOrgMember, IsOrgOwner, RequiresCsrfHeader

factory = APIRequestFactory()


def view_with(*permissions: Any) -> Callable[..., Any]:
    class Probe(APIView):
        permission_classes = [IsAuthenticated, *permissions]

        def get(self, request: Request) -> Response:
            return Response({"ok": True})

    return Probe.as_view()


def call(view: Callable[..., Any], membership: Membership) -> Any:
    request = factory.get("/probe/", HTTP_X_ORGANIZATION_ID=str(membership.organization_id))
    force_authenticate(request, user=membership.user)
    return view(request)


@pytest.mark.django_db
@pytest.mark.parametrize(
    ("permission", "role", "status"),
    [
        (IsOrgMember, Role.AGENT, 200),
        (IsOrgAdmin, Role.AGENT, 403),
        (IsOrgAdmin, Role.ADMIN, 200),
        (IsOrgOwner, Role.ADMIN, 403),
        (IsOrgOwner, Role.OWNER, 200),
    ],
)
def test_fixed_role_permissions(
    make_member: Callable[..., Membership], permission: Any, role: str, status: int
) -> None:
    response = call(view_with(permission), make_member(role=role))

    assert response.status_code == status
    if status == 403:
        assert response.data["error"]["code"] == "insufficient_role"


class CookieEndpoint(APIView):
    authentication_classes = [PublicEndpointAuthentication]
    permission_classes = [RequiresCsrfHeader]

    def post(self, request: Request) -> Response:
        raise InvalidCredentials()


def test_csrf_header_is_required_and_reported_as_403() -> None:
    response = CookieEndpoint.as_view()(factory.post("/cookie/"))

    assert response.status_code == 403
    assert response.data["error"]["code"] == "csrf_header_missing"


def test_public_endpoints_keep_401_with_a_challenge() -> None:
    request = factory.post("/cookie/", HTTP_X_REQUESTED_WITH="XMLHttpRequest")

    response = CookieEndpoint.as_view()(request)

    assert response.status_code == 401
    assert response["WWW-Authenticate"].startswith("Bearer")
    assert response.data["error"]["code"] == "invalid_credentials"
