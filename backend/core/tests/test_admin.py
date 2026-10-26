"""The Django admin pages for the backend-core models load, and staff can add a user with
the email login model (Django's stock user forms assume a username field)."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from django.test import Client

from accounts.models import Membership, User

ADMIN_PAGES = [
    "accounts/user",
    "accounts/organization",
    "accounts/invitation",
    "widget/widgetconfig",
    "billing/subscription",
    "billing/usagecounter",
    "billing/stripeevent",
]


@pytest.fixture
def staff_client(make_user: Callable[..., User]) -> Client:
    admin = make_user(email="root@example.com", is_staff=True, is_superuser=True)
    client = Client()
    client.force_login(admin)
    return client


@pytest.mark.django_db
@pytest.mark.parametrize("page", ADMIN_PAGES)
def test_changelists_and_add_forms_load(staff_client: Client, owner: Membership, page: str) -> None:
    assert staff_client.get(f"/admin/{page}/").status_code == 200
    assert staff_client.get(f"/admin/{page}/add/").status_code in (200, 403)


@pytest.mark.django_db
def test_staff_can_add_and_edit_a_user(staff_client: Client) -> None:
    response = staff_client.post(
        "/admin/accounts/user/add/",
        {
            "email": "New.Staff@Example.com",
            "password1": "a long passphrase",
            "password2": "a long passphrase",
        },
    )

    assert response.status_code == 302, response.content[:500]
    user = User.objects.get(email="new.staff@example.com")
    assert user.check_password("a long passphrase")
    assert staff_client.get(f"/admin/accounts/user/{user.pk}/change/").status_code == 200
