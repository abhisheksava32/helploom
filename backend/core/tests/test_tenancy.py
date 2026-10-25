"""Tenant scoping and role checks for dashboard views."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from rest_framework import generics, serializers
from rest_framework.test import APIRequestFactory, force_authenticate

from accounts.models import Membership, Role
from core.tenancy import OrganizationScopedMixin, resolve_membership


class MembershipSerializer(serializers.ModelSerializer):
    class Meta:
        model = Membership
        fields = ["id", "role"]


class MembershipListView(OrganizationScopedMixin, generics.ListCreateAPIView):
    queryset = Membership.objects.all()
    serializer_class = MembershipSerializer


def _call(method: str, membership: Membership, org_header: str | None = None) -> Any:
    factory = APIRequestFactory()
    headers = {"HTTP_X_ORGANIZATION_ID": org_header or str(membership.organization_id)}
    request = getattr(factory, method)("/members/", {}, format="json", **headers)
    force_authenticate(request, user=membership.user)
    return MembershipListView.as_view()(request)


@pytest.mark.django_db
def test_querysets_only_contain_the_callers_organization(make_member: Callable[..., Membership]) -> None:
    mine = make_member(role=Role.AGENT)
    make_member()  # another tenant

    response = _call("get", mine)

    assert response.status_code == 200
    assert [row["id"] for row in response.data["results"]] == [str(mine.id)]


@pytest.mark.django_db
def test_non_members_are_rejected(make_member: Callable[..., Membership]) -> None:
    mine = make_member()
    other = make_member()

    response = _call("get", mine, org_header=str(other.organization_id))

    assert response.status_code == 403
    assert response.data["error"]["code"] == "not_a_member"


@pytest.mark.django_db
def test_writes_need_the_write_role(make_member: Callable[..., Membership]) -> None:
    agent = make_member(role=Role.AGENT)

    response = _call("post", agent)

    assert response.status_code == 403
    assert response.data["error"]["code"] == "insufficient_role"


@pytest.mark.django_db
def test_without_a_header_the_oldest_membership_wins(make_member: Callable[..., Membership]) -> None:
    first = make_member()
    make_member(user=first.user)

    assert resolve_membership(first.user, None) == first
    assert resolve_membership(first.user, "not-a-uuid") is None
