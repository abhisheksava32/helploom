"""The Auth, Invitations and Organization endpoints in docs/API.md, including the refresh
cookie, its CSRF guard header, role checks and tenant isolation."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from django.conf import settings
from rest_framework.test import APIClient

from accounts import services
from accounts.models import Invitation, Membership, Organization, Role, User
from core.testing import access_token_for

PASSWORD = "a long passphrase for tests"
COOKIE = settings.REFRESH_COOKIE_NAME


def cookie_post(client: APIClient, path: str) -> Any:
    """POST to a cookie endpoint the way the dashboard does, with the CSRF guard header."""
    return client.post(path, HTTP_X_REQUESTED_WITH="XMLHttpRequest")


def signup(client: APIClient, email: str = "ada@example.com", **extra: Any) -> Any:
    body = {"email": email, "password": PASSWORD, "full_name": "Ada", "organization_name": "Northwind"}
    return client.post("/api/v1/auth/signup/", {**body, **extra}, format="json")


# Signup and login


@pytest.mark.django_db
def test_signup_returns_a_session_and_sets_the_refresh_cookie(api_client: APIClient) -> None:
    response = signup(api_client)

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {"access", "user", "organizations"}
    assert set(body["user"]) == {"id", "email", "full_name", "date_joined"}
    assert body["organizations"] == [
        {
            "id": body["organizations"][0]["id"],
            "name": "Northwind",
            "slug": "northwind",
            "assistant_tone": "friendly",
            "created_at": body["organizations"][0]["created_at"],
            "role": "owner",
        }
    ]
    cookie = response.cookies[COOKIE]
    assert cookie["httponly"]
    assert cookie["path"] == "/api/v1/auth/"
    assert cookie["samesite"] == "Lax"


@pytest.mark.django_db
def test_signup_validates_email_password_and_name(api_client: APIClient) -> None:
    signup(api_client)

    taken = signup(api_client, email="ADA@example.com")
    weak = signup(api_client, email="b@example.com", password="123456789012")
    short_name = signup(api_client, email="c@example.com", organization_name="N")

    assert taken.status_code == 400
    assert taken.json()["error"]["details"]["email"] == ["An account with this email already exists."]
    assert weak.json()["error"]["code"] == "validation_error"
    assert "password" in weak.json()["error"]["details"]
    assert "organization_name" in short_name.json()["error"]["details"]


@pytest.mark.django_db
def test_login_succeeds_and_failures_are_indistinguishable(
    api_client: APIClient, make_user: Callable[..., User]
) -> None:
    make_user(email="ada@example.com", password=PASSWORD)

    ok = api_client.post("/api/v1/auth/login/", {"email": "Ada@example.com", "password": PASSWORD})
    wrong = api_client.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": "nope nope"})
    unknown = api_client.post("/api/v1/auth/login/", {"email": "x@example.com", "password": PASSWORD})

    assert ok.status_code == 200
    assert COOKIE in ok.cookies
    for failed in (wrong, unknown):
        assert failed.status_code == 401
        assert failed.json()["error"]["code"] == "invalid_credentials"
        assert failed["WWW-Authenticate"].startswith("Bearer")
    assert wrong.json() == unknown.json()


@pytest.mark.django_db
def test_login_ignores_a_stale_bearer_token(make_user: Callable[..., User]) -> None:
    make_user(email="ada@example.com", password=PASSWORD)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Bearer expired.or.garbage")

    response = client.post("/api/v1/auth/login/", {"email": "ada@example.com", "password": PASSWORD})

    assert response.status_code == 200


# Refresh and logout


@pytest.mark.django_db
def test_refresh_rotates_the_cookie(api_client: APIClient) -> None:
    first_cookie = signup(api_client).cookies[COOKIE].value

    response = cookie_post(api_client, "/api/v1/auth/refresh/")

    assert response.status_code == 200
    assert set(response.json()) == {"access"}
    assert response.cookies[COOKIE].value != first_cookie

    replay = APIClient()
    replay.cookies[COOKIE] = first_cookie
    replayed = cookie_post(replay, "/api/v1/auth/refresh/")
    assert replayed.status_code == 401
    assert replayed.json()["error"]["code"] == "token_not_valid"
    assert replayed.cookies[COOKIE].value == ""  # cleared


@pytest.mark.django_db
def test_cookie_endpoints_require_the_csrf_header(api_client: APIClient) -> None:
    signup(api_client)

    refresh = api_client.post("/api/v1/auth/refresh/")
    logout = api_client.post("/api/v1/auth/logout/")

    for response in (refresh, logout):
        assert response.status_code == 403
        assert response.json()["error"]["code"] == "csrf_header_missing"


@pytest.mark.django_db
def test_refresh_without_a_cookie_is_401(api_client: APIClient) -> None:
    response = cookie_post(api_client, "/api/v1/auth/refresh/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "token_not_valid"


@pytest.mark.django_db
def test_logout_revokes_the_refresh_token(api_client: APIClient) -> None:
    cookie = signup(api_client).cookies[COOKIE].value

    response = cookie_post(api_client, "/api/v1/auth/logout/")

    assert response.status_code == 204
    assert response.cookies[COOKIE].value == ""
    reuse = APIClient()
    reuse.cookies[COOKIE] = cookie
    assert cookie_post(reuse, "/api/v1/auth/refresh/").status_code == 401
    assert cookie_post(APIClient(), "/api/v1/auth/logout/").status_code == 204  # no cookie


# Current user


@pytest.mark.django_db
def test_me_reads_and_updates_the_profile(auth_client: APIClient, owner: Membership) -> None:
    read = auth_client.get("/api/v1/auth/me/")
    updated = auth_client.patch("/api/v1/auth/me/", {"full_name": "Ada King"}, format="json")

    assert read.status_code == 200
    assert read.json()["user"]["email"] == owner.user.email
    assert [org["role"] for org in read.json()["organizations"]] == ["owner"]
    assert updated.json()["user"]["full_name"] == "Ada King"


def test_me_needs_a_token(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/auth/me/")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "not_authenticated"


@pytest.mark.django_db
def test_password_change(make_member: Callable[..., Membership]) -> None:
    membership = make_member()
    membership.user.set_password(PASSWORD)
    membership.user.save()
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token_for(membership.user)}")

    wrong = client.post(
        "/api/v1/auth/password/", {"current_password": "not it", "new_password": "a brand new passphrase"}
    )
    weak = client.post("/api/v1/auth/password/", {"current_password": PASSWORD, "new_password": "short"})
    ok = client.post(
        "/api/v1/auth/password/", {"current_password": PASSWORD, "new_password": "a brand new passphrase"}
    )

    assert "current_password" in wrong.json()["error"]["details"]
    assert "new_password" in weak.json()["error"]["details"]
    assert ok.status_code == 204
    assert ok.cookies[COOKIE].value  # the caller's session survives
    membership.user.refresh_from_db()
    assert membership.user.check_password("a brand new passphrase")


# Organization


@pytest.mark.django_db
def test_organization_read_and_update_by_role(
    owner: Membership, make_member: Callable[..., Membership], client_for: Callable[..., APIClient]
) -> None:
    agent = client_for(make_member(organization=owner.organization, role=Role.AGENT))
    admin = client_for(make_member(organization=owner.organization, role=Role.ADMIN))

    read = agent.get("/api/v1/organization/")
    denied = agent.patch("/api/v1/organization/", {"name": "Nope"}, format="json")
    updated = admin.patch("/api/v1/organization/", {"assistant_tone": "professional"}, format="json")
    invalid = admin.patch("/api/v1/organization/", {"assistant_tone": "sarcastic"}, format="json")

    assert read.json()["role"] == "agent"
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "insufficient_role"
    assert updated.json()["assistant_tone"] == "professional"
    assert updated.json()["role"] == "admin"
    assert invalid.status_code == 400


@pytest.mark.django_db
def test_requests_for_another_organization_are_refused(
    owner: Membership, make_organization: Callable[..., Organization]
) -> None:
    other = make_organization()
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access_token_for(owner.user)}", HTTP_X_ORGANIZATION_ID=str(other.id)
    )

    response = client.get("/api/v1/organization/")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "not_a_member"


@pytest.mark.django_db
def test_member_list_filters_searches_orders_and_isolates(
    owner: Membership,
    make_member: Callable[..., Membership],
    make_user: Callable[..., User],
    auth_client: APIClient,
) -> None:
    organization = owner.organization
    make_member(organization=organization, role=Role.AGENT, user=make_user(email="zed@example.com"))
    make_member(organization=organization, role=Role.ADMIN, user=make_user(email="amy@example.com"))
    make_member(role=Role.AGENT)  # another tenant

    listing = auth_client.get("/api/v1/organization/members/").json()
    agents = auth_client.get("/api/v1/organization/members/?role=agent").json()
    search = auth_client.get("/api/v1/organization/members/?search=AMY").json()
    by_email = auth_client.get("/api/v1/organization/members/?ordering=email").json()
    by_role = auth_client.get("/api/v1/organization/members/?ordering=role").json()
    bad_role = auth_client.get("/api/v1/organization/members/?role=boss")

    assert listing["count"] == 3
    assert set(listing["results"][0]) == {"id", "user", "role", "created_at"}
    assert [row["user"]["email"] for row in agents["results"]] == ["zed@example.com"]
    assert [row["user"]["email"] for row in search["results"]] == ["amy@example.com"]
    assert by_email["results"][0]["user"]["email"] == "amy@example.com"
    assert [row["role"] for row in by_role["results"]] == ["owner", "admin", "agent"]
    assert bad_role.status_code == 400


@pytest.mark.django_db
def test_changing_roles_is_owner_only_and_keeps_an_owner(
    owner: Membership,
    make_member: Callable[..., Membership],
    client_for: Callable[..., APIClient],
    auth_client: APIClient,
) -> None:
    admin = make_member(organization=owner.organization, role=Role.ADMIN)
    agent = make_member(organization=owner.organization, role=Role.AGENT)
    url = f"/api/v1/organization/members/{agent.id}/"

    by_admin = client_for(admin).patch(url, {"role": "admin"}, format="json")
    by_owner = auth_client.patch(url, {"role": "admin"}, format="json")
    last_owner = auth_client.patch(
        f"/api/v1/organization/members/{owner.id}/", {"role": "agent"}, format="json"
    )

    assert by_admin.status_code == 403
    assert by_owner.json()["role"] == "admin"
    assert last_owner.status_code == 409
    assert last_owner.json()["error"]["code"] == "last_owner"


@pytest.mark.django_db
def test_removing_members(
    owner: Membership,
    make_member: Callable[..., Membership],
    client_for: Callable[..., APIClient],
    auth_client: APIClient,
) -> None:
    agent = make_member(organization=owner.organization, role=Role.AGENT)
    other_agent = make_member(organization=owner.organization, role=Role.AGENT)
    stranger = make_member()

    denied = client_for(agent).delete(f"/api/v1/organization/members/{other_agent.id}/")
    left = client_for(agent).delete(f"/api/v1/organization/members/{agent.id}/")
    foreign = auth_client.delete(f"/api/v1/organization/members/{stranger.id}/")

    assert denied.status_code == 403
    assert left.status_code == 204
    assert foreign.status_code == 404
    assert Membership.objects.filter(pk=stranger.pk).exists()


# Invitations


@pytest.mark.django_db
def test_invitation_create_list_resend_and_revoke(
    auth_client: APIClient, owner: Membership, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        created = auth_client.post(
            "/api/v1/organization/invitations/", {"email": "new@example.com", "role": "agent"}, format="json"
        )
    duplicate = auth_client.post(
        "/api/v1/organization/invitations/", {"email": "new@example.com"}, format="json"
    )
    invitation_id = created.json()["id"]
    resent = auth_client.post(f"/api/v1/organization/invitations/{invitation_id}/resend/")
    listing = auth_client.get("/api/v1/organization/invitations/?status=pending").json()
    revoked = auth_client.delete(f"/api/v1/organization/invitations/{invitation_id}/")
    again = auth_client.delete(f"/api/v1/organization/invitations/{invitation_id}/")

    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "pending"
    assert body["invited_by"]["email"] == owner.user.email
    assert body["invite_url"] is None  # tests run with DEBUG off
    assert duplicate.json()["error"]["code"] == "already_invited"
    assert resent.status_code == 200
    assert [row["id"] for row in listing["results"]] == [invitation_id]
    assert listing["results"][0]["invite_url"] is None
    assert revoked.status_code == 204
    assert again.json()["error"] == {
        "code": "invitation_not_pending",
        "message": "This invitation was revoked.",
        "details": {"status": "revoked"},
    }


@pytest.mark.django_db
def test_invite_url_is_returned_only_in_debug(auth_client: APIClient, settings: Any) -> None:
    settings.DEBUG = True

    body = auth_client.post("/api/v1/organization/invitations/", {"email": "dev@example.com"}).json()

    assert body["invite_url"].startswith(f"{settings.FRONTEND_URL}/invite/")


@pytest.mark.django_db
def test_invitations_are_admin_only_and_seat_limited(
    owner: Membership,
    make_member: Callable[..., Membership],
    client_for: Callable[..., APIClient],
    auth_client: APIClient,
) -> None:
    agent = client_for(make_member(organization=owner.organization, role=Role.AGENT))

    listing = agent.get("/api/v1/organization/invitations/")
    full = auth_client.post("/api/v1/organization/invitations/", {"email": "third@example.com"})

    assert listing.status_code == 403
    assert full.status_code == 402  # owner + agent fill the two Free seats
    assert full.json()["error"]["details"] == {"limit": "seats", "used": 2, "allowed": 2, "plan": "free"}


@pytest.mark.django_db
def test_public_invitation_lookup_and_new_account_accept(api_client: APIClient, owner: Membership) -> None:
    issued = services.invite(
        organization=owner.organization, email="grace@example.com", role="agent", actor=owner
    )

    lookup = api_client.get(f"/api/v1/invitations/{issued.raw_token}/")
    accepted = api_client.post(
        f"/api/v1/invitations/{issued.raw_token}/accept/",
        {"full_name": "Grace Hopper", "password": PASSWORD},
        format="json",
    )
    unknown = api_client.get("/api/v1/invitations/not-a-real-token/")

    assert lookup.json() == {
        "organization": {"id": str(owner.organization_id), "name": owner.organization.name},
        "email": "grace@example.com",
        "role": "agent",
        "status": "pending",
        "expires_at": lookup.json()["expires_at"],
        "invited_by_name": owner.user.email,
        "account_exists": False,
    }
    assert accepted.status_code == 200
    assert COOKIE in accepted.cookies
    assert [org["role"] for org in accepted.json()["organizations"]] == ["agent"]
    assert unknown.status_code == 404


@pytest.mark.django_db
def test_signed_in_accept(
    owner: Membership, make_user: Callable[..., User], client_for: Callable[..., APIClient]
) -> None:
    grace = make_user(email="grace@example.com")
    issued = services.invite(
        organization=owner.organization, email="grace@example.com", role="admin", actor=owner
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token_for(grace)}")

    response = client.post(f"/api/v1/invitations/{issued.raw_token}/accept/", {}, format="json")
    again = client.post(f"/api/v1/invitations/{issued.raw_token}/accept/", {}, format="json")

    assert response.status_code == 200
    assert Membership.objects.get(user=grace).role == Role.ADMIN
    assert again.json()["error"]["code"] == "invitation_not_pending"
    assert Invitation.objects.get(pk=issued.invitation.pk).accepted_by == grace
