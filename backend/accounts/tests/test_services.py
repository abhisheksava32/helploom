"""Signup, sessions, member management (last owner rule) and the invitation lifecycle."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any

import pytest
from django.core import mail
from django.utils import timezone
from rest_framework import exceptions
from rest_framework_simplejwt.exceptions import InvalidToken
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken

from accounts import services
from accounts.models import Invitation, InvitationStatus, Membership, Organization, Role, User
from billing.models import Subscription
from core.exceptions import Conflict, InvalidCredentials, PlanLimitExceeded
from widget.models import WidgetConfig

PASSWORD = "a long passphrase for tests"


# Signup and sessions


@pytest.mark.django_db
def test_signup_creates_a_complete_workspace() -> None:
    membership = services.signup(
        email="Ada@Example.com", password=PASSWORD, full_name="Ada", organization_name="Northwind Outfitters"
    )

    organization = membership.organization
    assert membership.role == Role.OWNER
    assert membership.user.email == "ada@example.com"
    assert organization.slug == "northwind-outfitters"
    assert Subscription.objects.get(organization=organization).plan == "free"
    assert WidgetConfig.objects.filter(organization=organization).exists()


@pytest.mark.django_db
def test_signup_gives_each_workspace_a_unique_slug() -> None:
    first = services.signup(email="a@example.com", password=PASSWORD, organization_name="Acme")
    second = services.signup(email="b@example.com", password=PASSWORD, organization_name="ACME")

    assert first.organization.slug == "acme"
    assert second.organization.slug.startswith("acme-")
    assert second.organization.slug != first.organization.slug


@pytest.mark.django_db
def test_signup_with_a_taken_email_is_a_validation_error(make_user: Callable[..., User]) -> None:
    make_user(email="taken@example.com")

    with pytest.raises(exceptions.ValidationError) as excinfo:
        services.signup(email="taken@example.com", password=PASSWORD, organization_name="Acme")

    assert "email" in excinfo.value.detail
    assert not Organization.objects.filter(name="Acme").exists()


def test_password_rules_include_similarity_to_the_email() -> None:
    assert services.password_errors("short", email="a@example.com")
    assert services.password_errors("adalovelace1", email="adalovelace1@example.com")
    assert services.password_errors(PASSWORD, email="a@example.com") == []


@pytest.mark.django_db
def test_login_uses_one_error_for_unknown_email_and_wrong_password(make_user: Callable[..., User]) -> None:
    user = make_user(email="ada@example.com", password=PASSWORD)

    assert services.authenticate_credentials(email="ADA@example.com", password=PASSWORD) == user
    with pytest.raises(InvalidCredentials):
        services.authenticate_credentials(email="ada@example.com", password="wrong password here")
    with pytest.raises(InvalidCredentials):
        services.authenticate_credentials(email="nobody@example.com", password=PASSWORD)
    user.refresh_from_db()
    assert user.last_login is not None


@pytest.mark.django_db
def test_refresh_tokens_rotate_and_are_single_use(make_user: Callable[..., User]) -> None:
    pair = services.issue_tokens(make_user())

    rotated = services.rotate_refresh_token(pair.refresh)

    assert rotated.refresh != pair.refresh
    with pytest.raises(InvalidToken):
        services.rotate_refresh_token(pair.refresh)  # replay
    assert services.rotate_refresh_token(rotated.refresh).access


@pytest.mark.django_db
@pytest.mark.parametrize("raw", [None, "", "not-a-jwt"])
def test_refresh_refuses_missing_and_malformed_tokens(raw: str | None) -> None:
    with pytest.raises(InvalidToken):
        services.rotate_refresh_token(raw)


@pytest.mark.django_db
def test_refresh_refuses_inactive_users(make_user: Callable[..., User]) -> None:
    user = make_user()
    pair = services.issue_tokens(user)
    user.is_active = False
    user.save()

    with pytest.raises(InvalidToken):
        services.rotate_refresh_token(pair.refresh)


@pytest.mark.django_db
def test_logout_blacklists_and_tolerates_garbage(make_user: Callable[..., User]) -> None:
    pair = services.issue_tokens(make_user())

    services.revoke_refresh_token(pair.refresh)
    services.revoke_refresh_token("garbage")
    services.revoke_refresh_token(None)

    with pytest.raises(InvalidToken):
        services.rotate_refresh_token(pair.refresh)


@pytest.mark.django_db
def test_changing_the_password_signs_out_other_sessions(make_user: Callable[..., User]) -> None:
    user = make_user(password=PASSWORD)
    other_session = services.issue_tokens(user)

    mine = services.change_password(user, new_password="another long passphrase")

    user.refresh_from_db()
    assert user.check_password("another long passphrase")
    with pytest.raises(InvalidToken):
        services.rotate_refresh_token(other_session.refresh)
    assert services.rotate_refresh_token(mine.refresh).access
    live = OutstandingToken.objects.filter(user=user, blacklistedtoken__isnull=True)
    assert live.count() == 1
    assert BlacklistedToken.objects.filter(token__user=user).count() >= 2


# Organisation and members


@pytest.mark.django_db
def test_update_organization_changes_only_given_fields(organization: Organization) -> None:
    services.update_organization(organization, assistant_tone="concise")
    organization.refresh_from_db()
    assert organization.assistant_tone == "concise"

    services.update_organization(organization, name="  Northwind  ")
    organization.refresh_from_db()
    assert (organization.name, organization.assistant_tone) == ("Northwind", "concise")


@pytest.mark.django_db
def test_the_last_owner_cannot_be_demoted_or_removed(owner: Membership) -> None:
    with pytest.raises(Conflict) as excinfo:
        services.change_member_role(member=owner, role=Role.ADMIN)
    assert excinfo.value.get_codes() == "last_owner"

    with pytest.raises(Conflict):
        services.remove_member(actor=owner, member=owner)


@pytest.mark.django_db
def test_an_owner_can_step_down_when_another_owner_exists(
    owner: Membership, make_member: Callable[..., Membership]
) -> None:
    make_member(organization=owner.organization, role=Role.OWNER)

    assert services.change_member_role(member=owner, role=Role.AGENT).role == Role.AGENT


@pytest.mark.django_db
def test_member_removal_rules(owner: Membership, make_member: Callable[..., Membership]) -> None:
    organization = owner.organization
    admin = make_member(organization=organization, role=Role.ADMIN)
    agent = make_member(organization=organization, role=Role.AGENT)
    other_agent = make_member(organization=organization, role=Role.AGENT)

    with pytest.raises(exceptions.PermissionDenied):
        services.remove_member(actor=agent, member=other_agent)
    with pytest.raises(exceptions.PermissionDenied):
        services.remove_member(actor=admin, member=owner)

    services.remove_member(actor=agent, member=agent)  # leaving is always allowed
    services.remove_member(actor=admin, member=other_agent)
    services.remove_member(actor=owner, member=admin)

    assert list(Membership.objects.for_organization(organization)) == [owner]


# Invitations


def invite(organization: Organization, actor: Membership, email: str = "new@example.com", **kw: Any) -> Any:
    return services.invite(
        organization=organization, email=email, role=kw.get("role", Role.AGENT), actor=actor
    )


@pytest.mark.django_db
def test_invitations_are_emailed_after_commit(
    owner: Membership, django_capture_on_commit_callbacks: Any
) -> None:
    with django_capture_on_commit_callbacks(execute=True):
        issued = invite(owner.organization, owner, email="New@Example.com")

    invitation = issued.invitation
    assert invitation.email == "new@example.com"
    assert invitation.status == InvitationStatus.PENDING
    assert len(mail.outbox) == 1
    assert issued.url in mail.outbox[0].body
    assert mail.outbox[0].to == ["new@example.com"]
    assert issued.raw_token not in invitation.token_hash


@pytest.mark.django_db
def test_only_owners_invite_owners(owner: Membership, make_member: Callable[..., Membership]) -> None:
    Subscription.objects.create(organization=owner.organization, plan="starter")
    admin = make_member(organization=owner.organization, role=Role.ADMIN)

    with pytest.raises(exceptions.PermissionDenied):
        invite(owner.organization, admin, role=Role.OWNER)
    assert invite(owner.organization, owner, role=Role.OWNER).invitation.role == Role.OWNER


@pytest.mark.django_db
def test_inviting_members_or_pending_emails_conflicts(owner: Membership) -> None:
    with pytest.raises(Conflict) as member_conflict:
        invite(owner.organization, owner, email=owner.user.email)
    assert member_conflict.value.get_codes() == "already_member"

    invite(owner.organization, owner)
    with pytest.raises(Conflict) as invite_conflict:
        invite(owner.organization, owner)
    assert invite_conflict.value.get_codes() == "already_invited"


@pytest.mark.django_db
def test_invitations_respect_the_seat_limit(owner: Membership) -> None:
    invite(owner.organization, owner, email="second@example.com")  # Free has 2 seats

    with pytest.raises(PlanLimitExceeded) as excinfo:
        invite(owner.organization, owner, email="third@example.com")
    assert excinfo.value.details["limit"] == "seats"


@pytest.mark.django_db
def test_an_expired_invitation_is_reused_when_inviting_again(owner: Membership) -> None:
    first = invite(owner.organization, owner).invitation
    Invitation.objects.filter(pk=first.pk).update(expires_at=timezone.now() - timedelta(days=1))

    again = invite(owner.organization, owner, role=Role.ADMIN).invitation

    assert again.pk == first.pk
    assert again.role == Role.ADMIN
    assert again.status == InvitationStatus.PENDING


@pytest.mark.django_db
def test_resend_issues_a_new_token_and_revoke_ends_it(owner: Membership) -> None:
    issued = invite(owner.organization, owner)

    resent = services.resend_invitation(issued.invitation)

    assert resent.raw_token != issued.raw_token
    with pytest.raises(exceptions.NotFound):
        services.get_invitation_by_token(issued.raw_token)
    assert services.get_invitation_by_token(resent.raw_token) == issued.invitation

    services.revoke_invitation(resent.invitation)
    with pytest.raises(Conflict) as excinfo:
        services.resend_invitation(resent.invitation)
    assert excinfo.value.details == {"status": "revoked"}
    with pytest.raises(Conflict):
        services.revoke_invitation(resent.invitation)


@pytest.mark.django_db
def test_accepting_with_a_new_account(owner: Membership) -> None:
    issued = invite(owner.organization, owner, email="grace@example.com")

    membership = services.accept_invitation(
        raw_token=issued.raw_token, user=None, full_name="Grace Hopper", password=PASSWORD
    )

    assert membership.organization == owner.organization
    assert membership.role == Role.AGENT
    assert membership.user.full_name == "Grace Hopper"
    issued.invitation.refresh_from_db()
    assert issued.invitation.status == InvitationStatus.ACCEPTED
    assert issued.invitation.accepted_by == membership.user

    with pytest.raises(Conflict) as excinfo:
        services.accept_invitation(raw_token=issued.raw_token, user=membership.user)
    assert excinfo.value.details == {"status": "accepted"}


@pytest.mark.django_db
def test_accepting_while_signed_in(owner: Membership, make_user: Callable[..., User]) -> None:
    grace = make_user(email="grace@example.com")
    stranger = make_user(email="stranger@example.com")
    issued = invite(owner.organization, owner, email="grace@example.com")

    with pytest.raises(exceptions.PermissionDenied) as mismatch:
        services.accept_invitation(raw_token=issued.raw_token, user=stranger)
    assert mismatch.value.get_codes() == "email_mismatch"
    with pytest.raises(Conflict) as exists:
        services.accept_invitation(raw_token=issued.raw_token, user=None, password=PASSWORD)
    assert exists.value.get_codes() == "account_exists"

    membership = services.accept_invitation(raw_token=issued.raw_token, user=grace)
    assert membership.user == grace


@pytest.mark.django_db
def test_accepting_rejects_weak_passwords_and_unknown_tokens(owner: Membership) -> None:
    issued = invite(owner.organization, owner, email="grace@example.com")

    with pytest.raises(exceptions.ValidationError) as weak:
        services.accept_invitation(raw_token=issued.raw_token, user=None, password="12345")
    assert "password" in weak.value.detail
    with pytest.raises(exceptions.NotFound):
        services.accept_invitation(raw_token="unknown", user=None, password=PASSWORD)
    assert not User.objects.filter(email="grace@example.com").exists()


@pytest.mark.django_db
def test_invitation_status_filters_match_the_derived_status(owner: Membership) -> None:
    pending = invite(owner.organization, owner, email="p@example.com").invitation
    expired = Invitation.objects.create(
        organization=owner.organization,
        email="e@example.com",
        token_hash="e" * 64,
        expires_at=timezone.now() - timedelta(hours=1),
    )

    for status, expected in [("pending", pending), ("expired", expired)]:
        found = Invitation.objects.filter(services.invitation_status_filter(status))
        assert list(found) == [expected]
        assert expected.status == status
