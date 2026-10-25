"""Shared pytest fixtures. Owner: backend-core; app specific fixtures belong in that
app's tests/conftest.py.

Factories are plain functions rather than a factory library: the models are small and
explicit setup keeps each test readable.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable
from typing import Any

import pytest
from rest_framework.test import APIClient

from accounts.models import Membership, Organization, Role, User
from core.testing import access_token_for

_sequence = itertools.count(1)


@pytest.fixture
def make_user(db: None) -> Callable[..., User]:
    def factory(email: str | None = None, password: str = "correct-horse-battery", **extra: Any) -> User:
        email = email or f"user{next(_sequence)}@example.com"
        return User.objects.create_user(email=email, password=password, **extra)

    return factory


@pytest.fixture
def make_organization(db: None) -> Callable[..., Organization]:
    def factory(name: str | None = None, **extra: Any) -> Organization:
        number = next(_sequence)
        return Organization.objects.create(
            name=name or f"Org {number}", slug=extra.pop("slug", f"org-{number}"), **extra
        )

    return factory


@pytest.fixture
def make_member(
    make_user: Callable[..., User], make_organization: Callable[..., Organization]
) -> Callable[..., Membership]:
    def factory(
        organization: Organization | None = None, role: str = Role.OWNER, user: User | None = None
    ) -> Membership:
        return Membership.objects.create(
            organization=organization or make_organization(),
            user=user or make_user(),
            role=role,
        )

    return factory


@pytest.fixture
def owner(make_member: Callable[..., Membership]) -> Membership:
    return make_member(role=Role.OWNER)


@pytest.fixture
def organization(owner: Membership) -> Organization:
    return owner.organization


@pytest.fixture
def api_client() -> APIClient:
    return APIClient()


@pytest.fixture
def auth_client(owner: Membership) -> APIClient:
    """An API client signed in as the owner, scoped to the owner's organisation."""
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(owner.user)}",
        HTTP_X_ORGANIZATION_ID=str(owner.organization_id),
    )
    return client
