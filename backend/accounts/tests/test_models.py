"""Users, organisations, memberships and invitations."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta

import pytest
from django.db import IntegrityError
from django.utils import timezone

from accounts.models import (
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
    User,
    hash_invitation_token,
)


@pytest.mark.django_db
def test_emails_are_normalised_and_unique_ignoring_case(make_user: Callable[..., User]) -> None:
    user = make_user(email="  Ada@Example.COM ")

    assert user.email == "ada@example.com"
    with pytest.raises(IntegrityError):
        User.objects.create(email="ADA@example.com")


@pytest.mark.django_db
def test_a_user_joins_an_organization_once(owner: Membership) -> None:
    with pytest.raises(IntegrityError):
        Membership.objects.create(user=owner.user, organization=owner.organization, role="agent")


@pytest.mark.django_db
def test_invitation_tokens_are_stored_hashed(organization: Organization) -> None:
    raw, digest = Invitation.new_token()
    invitation = Invitation.objects.create(
        organization=organization,
        email="New.Teammate@example.com",
        token_hash=digest,
        expires_at=timezone.now() + timedelta(days=7),
    )

    assert invitation.email == "new.teammate@example.com"
    assert invitation.token_hash == hash_invitation_token(raw)
    assert raw not in invitation.token_hash
    assert invitation.status == InvitationStatus.PENDING


@pytest.mark.django_db
def test_invitation_status_follows_its_timestamps(organization: Organization) -> None:
    invitation = Invitation(
        organization=organization, email="a@example.com", expires_at=timezone.now() - timedelta(minutes=1)
    )
    assert invitation.status == InvitationStatus.EXPIRED

    invitation.revoked_at = timezone.now()
    assert invitation.status == InvitationStatus.REVOKED

    invitation.accepted_at = timezone.now()
    assert invitation.status == InvitationStatus.ACCEPTED
