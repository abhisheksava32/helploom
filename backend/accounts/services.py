"""Account business logic: signup, sessions, profiles, organisations, members and
invitations. Views validate input with accounts.serializers and call one function here.

Rules worth knowing:

- Signup creates the user, the organisation, the owner membership, a Free demo
  subscription and the widget settings in one transaction.
- Sessions are a short lived access JWT plus a rotating refresh token (stored as an
  httpOnly cookie by the views). A refresh token is single use: rotating blacklists
  it under a row lock, so a replayed token is refused even under concurrency. The one
  exception is a short reuse grace (REFRESH_REUSE_GRACE_SECONDS) for a token that was
  just rotated: a page reload can cancel the refresh request after the server rotated
  but before the browser stored the new cookie, and without the grace that race signs
  the user out. Logout and password changes end the grace at once.
- An organisation always keeps at least one owner.
- Invitation tokens are emailed once and stored only as SHA-256 hashes.
"""

from __future__ import annotations

import logging
import secrets
import string
import time
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import UUID

from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import password_validation as pv
from django.contrib.auth.models import update_last_login
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.mail import send_mail
from django.db import IntegrityError, transaction
from django.db.models import Q, QuerySet
from django.utils import timezone
from django.utils.text import slugify
from rest_framework import exceptions
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from rest_framework_simplejwt.settings import api_settings as jwt_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import RefreshToken

from billing import services as billing_services
from core.exceptions import Conflict, InvalidCredentials
from core.permissions import has_role
from widget import services as widget_services

from .models import (
    Invitation,
    InvitationStatus,
    Membership,
    Organization,
    Role,
    User,
    hash_invitation_token,
    normalize_email,
)

logger = logging.getLogger(__name__)

EMAIL_TAKEN = "An account with this email already exists."
SESSION_EXPIRED = "Your session has expired. Please sign in again."
LAST_OWNER = "An organization needs at least one owner. Make someone else an owner first."


@dataclass(frozen=True)
class TokenPair:
    access: str
    refresh: str


@dataclass(frozen=True)
class IssuedInvitation:
    """The raw token exists only here, long enough to email it (and, in DEBUG, to
    return the link to the admin who created it)."""

    invitation: Invitation
    raw_token: str

    @property
    def url(self) -> str:
        return invite_url(self.raw_token)


# Signup and organisations


def password_errors(password: str, *, email: str, full_name: str = "") -> list[str]:
    """Django's validators, run against an unsaved user so the similarity check can
    compare the password with the email and name."""
    try:
        pv.validate_password(password, user=User(email=email, full_name=full_name))
    except DjangoValidationError as exc:
        return list(exc.messages)
    return []


def signup(*, email: str, password: str, organization_name: str, full_name: str = "") -> Membership:
    with transaction.atomic():
        try:
            with transaction.atomic():
                user = User.objects.create_user(email=email, password=password, full_name=full_name)
        except IntegrityError as exc:
            # The serializer checked first; this catches two signups racing.
            raise exceptions.ValidationError({"email": [EMAIL_TAKEN]}) from exc
        organization = create_organization(name=organization_name)
        return Membership.objects.create(user=user, organization=organization, role=Role.OWNER)


def create_organization(*, name: str) -> Organization:
    """A workspace with everything it needs to work: subscription and widget settings."""
    name = name.strip()
    organization = _create_with_unique_slug(name)
    billing_services.create_subscription(organization)
    widget_services.create_widget(organization)
    return organization


def _create_with_unique_slug(name: str) -> Organization:
    base = slugify(name)[:50].strip("-") or "workspace"
    alphabet = string.ascii_lowercase + string.digits
    candidates = [base] + [f"{base}-{''.join(secrets.choice(alphabet) for _ in range(6))}" for _ in range(5)]
    for slug in candidates:
        if Organization.objects.filter(slug=slug).exists():
            continue
        try:
            with transaction.atomic():
                return Organization.objects.create(name=name, slug=slug)
        except IntegrityError:
            continue  # taken between the check and the insert
    raise Conflict("Could not create the workspace. Please try again.", code="slug_unavailable")


def memberships_for(user: User) -> QuerySet[Membership]:
    """Every organisation the user belongs to, oldest membership first."""
    return Membership.objects.filter(user=user).select_related("organization").order_by("created_at")


def update_organization(
    organization: Organization, *, name: str | None = None, assistant_tone: str | None = None
) -> Organization:
    fields = []
    if name is not None:
        organization.name = name.strip()
        fields.append("name")
    if assistant_tone is not None:
        organization.assistant_tone = assistant_tone
        fields.append("assistant_tone")
    if fields:
        organization.save(update_fields=[*fields, "updated_at"])
    return organization


# Sessions


def authenticate_credentials(*, email: str, password: str) -> User:
    user = authenticate(email=normalize_email(email), password=password)
    if not isinstance(user, User):
        raise InvalidCredentials()
    update_last_login(User, user)
    return user


def issue_tokens(user: User) -> TokenPair:
    refresh = RefreshToken.for_user(user)
    return TokenPair(access=str(refresh.access_token), refresh=str(refresh))


class _UncheckedBlacklistRefreshToken(RefreshToken):
    """Verifies signature, expiry and type but leaves the blacklist to
    rotate_refresh_token, which checks it under a row lock and applies the reuse grace."""

    def check_blacklist(self) -> None:
        return None


def _rotation_key(jti: str) -> str:
    return f"auth:refresh-rotated:{jti}"


def _revocation_key(user_id: object) -> str:
    return f"auth:sessions-revoked:{user_id}"


def _remember_rotation(jti: str, user_id: object) -> None:
    grace = settings.REFRESH_REUSE_GRACE_SECONDS
    if grace > 0:
        cache.set(_rotation_key(jti), {"user_id": str(user_id), "at": time.time()}, timeout=grace)


def _within_reuse_grace(jti: str, user_id: object) -> bool:
    """True when this blacklisted token was rotated moments ago and no logout or
    password change happened since."""
    entry = cache.get(_rotation_key(jti))
    if not isinstance(entry, dict) or entry.get("user_id") != str(user_id):
        return False
    revoked_at = cache.get(_revocation_key(user_id))
    return revoked_at is None or float(revoked_at) < float(entry["at"])


def _end_reuse_grace(user_id: object) -> None:
    grace = settings.REFRESH_REUSE_GRACE_SECONDS
    if grace > 0:
        # Kept a little longer than the grace so it outlives every rotation entry.
        cache.set(_revocation_key(user_id), time.time(), timeout=grace + 5)


def rotate_refresh_token(raw: str | None) -> TokenPair:
    """Exchange a refresh token for a new pair and retire the old one."""
    if not raw:
        raise InvalidToken(SESSION_EXPIRED)
    try:
        token = _UncheckedBlacklistRefreshToken(raw)  # type: ignore[arg-type]
    except TokenError as exc:
        raise InvalidToken(SESSION_EXPIRED) from exc

    jti = str(token[jwt_settings.JTI_CLAIM])
    with transaction.atomic():
        # The row lock makes "is it blacklisted?" and "blacklist it" one step, so two
        # requests replaying the same token cannot both get a new session.
        # order_by() drops the model's default ordering by user, an outer join that
        # PostgreSQL refuses to lock.
        outstanding = (
            OutstandingToken.objects.select_for_update(of=("self",)).filter(jti=jti).order_by().first()
        )
        if outstanding is None:
            raise InvalidToken(SESSION_EXPIRED)
        user = User.objects.filter(pk=token.get(jwt_settings.USER_ID_CLAIM), is_active=True).first()
        if user is None:
            raise InvalidToken(SESSION_EXPIRED)
        if BlacklistedToken.objects.filter(token=outstanding).exists():
            if not _within_reuse_grace(jti, user.pk):
                raise InvalidToken(SESSION_EXPIRED)
            return issue_tokens(user)
        BlacklistedToken.objects.create(token=outstanding)
        _remember_rotation(jti, user.pk)
        return issue_tokens(user)


def revoke_refresh_token(raw: str | None) -> None:
    """Logout. An invalid or missing token needs no revoking."""
    if not raw:
        return
    try:
        token = RefreshToken(raw)  # type: ignore[arg-type]
        token.blacklist()
    except TokenError:
        return
    _end_reuse_grace(token.get(jwt_settings.USER_ID_CLAIM))


def revoke_all_sessions(user: User) -> None:
    live = OutstandingToken.objects.filter(
        user=user, expires_at__gt=timezone.now(), blacklistedtoken__isnull=True
    )
    BlacklistedToken.objects.bulk_create(
        [BlacklistedToken(token=token) for token in live], ignore_conflicts=True
    )
    _end_reuse_grace(user.pk)


def update_profile(user: User, *, full_name: str | None = None) -> User:
    if full_name is not None:
        user.full_name = full_name.strip()
        user.save(update_fields=["full_name"])
    return user


def change_password(user: User, *, new_password: str) -> TokenPair:
    """Set the new password, sign out every other session and return a fresh pair for
    the caller's own session. Other sessions keep their access token until it expires
    (at most JWT_ACCESS_MINUTES) and then cannot refresh."""
    with transaction.atomic():
        user.set_password(new_password)
        user.save(update_fields=["password"])
        revoke_all_sessions(user)
        return issue_tokens(user)


# Members


def _lock_owners(organization_id: UUID) -> list[UUID]:
    return list(
        Membership.objects.select_for_update()
        .filter(organization_id=organization_id, role=Role.OWNER)
        .values_list("id", flat=True)
    )


def _ensure_another_owner(member: Membership) -> None:
    owners = _lock_owners(member.organization_id)
    if owners == [member.pk]:
        raise Conflict(LAST_OWNER, code="last_owner")


def change_member_role(*, member: Membership, role: str) -> Membership:
    with transaction.atomic():
        member = Membership.objects.select_for_update().select_related("user").get(pk=member.pk)
        if member.role == role:
            return member
        if member.role == Role.OWNER:
            _ensure_another_owner(member)
        member.role = role
        member.save(update_fields=["role", "updated_at"])
        return member


def remove_member(*, actor: Membership, member: Membership) -> None:
    """Admins remove agents and admins, owners remove anyone, everyone may leave."""
    if member.user_id != actor.user_id:
        if not has_role(actor.role, Role.ADMIN):
            raise exceptions.PermissionDenied(
                "This action needs the admin role or higher.", code="insufficient_role"
            )
        if member.role == Role.OWNER and actor.role != Role.OWNER:
            raise exceptions.PermissionDenied(
                "Only an owner can remove another owner.", code="insufficient_role"
            )
    with transaction.atomic():
        member = Membership.objects.select_for_update().get(pk=member.pk)
        if member.role == Role.OWNER:
            _ensure_another_owner(member)
        member.delete()


# Invitations


def invite_url(raw_token: str) -> str:
    return f"{settings.FRONTEND_URL}/invite/{raw_token}"


def invitation_status_filter(status: str) -> Q:
    """The derived status as a query, for ?status= on the invitation list."""
    now = timezone.now()
    open_ = Q(accepted_at__isnull=True, revoked_at__isnull=True)
    return {
        InvitationStatus.PENDING: open_ & Q(expires_at__gt=now),
        InvitationStatus.EXPIRED: open_ & Q(expires_at__lte=now),
        InvitationStatus.ACCEPTED: Q(accepted_at__isnull=False),
        InvitationStatus.REVOKED: Q(accepted_at__isnull=True, revoked_at__isnull=False),
    }[InvitationStatus(status)]


def _new_expiry() -> datetime:
    return timezone.now() + timedelta(days=settings.INVITATION_EXPIRY_DAYS)


def _not_pending(invitation: Invitation) -> Conflict:
    messages: dict[str, str] = {
        InvitationStatus.ACCEPTED: "This invitation has already been accepted.",
        InvitationStatus.REVOKED: "This invitation was revoked.",
        InvitationStatus.EXPIRED: "This invitation has expired. Ask for a new one.",
    }
    status = invitation.status
    return Conflict(
        messages.get(status, "This invitation is no longer pending."),
        code="invitation_not_pending",
        details={"status": str(status)},
    )


def invite(*, organization: Organization, email: str, role: str, actor: Membership) -> IssuedInvitation:
    if role == Role.OWNER and actor.role != Role.OWNER:
        raise exceptions.PermissionDenied("Only an owner can invite another owner.", code="insufficient_role")
    email = normalize_email(email)
    raw, digest = Invitation.new_token()
    with transaction.atomic():
        # One invite at a time per organisation, so two admins cannot both take the
        # last free seat.
        Organization.objects.select_for_update().filter(pk=organization.pk).first()
        if Membership.objects.filter(organization=organization, user__email=email).exists():
            raise Conflict(f"{email} is already a member of this organization.", code="already_member")
        open_invitation = (
            Invitation.objects.select_for_update()
            .filter(organization=organization, email=email, accepted_at__isnull=True, revoked_at__isnull=True)
            .first()
        )
        if open_invitation is not None and open_invitation.status == InvitationStatus.PENDING:
            raise Conflict(
                f"{email} already has a pending invitation. Resend it instead.", code="already_invited"
            )
        billing_services.ensure_seat_quota(organization)
        if open_invitation is not None:
            # An expired invite still holds the "one open invite per email" slot; reuse it.
            invitation = open_invitation
            invitation.role = role
            invitation.invited_by = actor.user
            invitation.token_hash = digest
            invitation.expires_at = _new_expiry()
            invitation.save()
        else:
            invitation = Invitation.objects.create(
                organization=organization,
                email=email,
                role=role,
                invited_by=actor.user,
                token_hash=digest,
                expires_at=_new_expiry(),
            )
        _email_after_commit(invitation.pk, raw)
    return IssuedInvitation(invitation=invitation, raw_token=raw)


def resend_invitation(invitation: Invitation) -> IssuedInvitation:
    raw, digest = Invitation.new_token()
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        status = invitation.status
        if status in (InvitationStatus.ACCEPTED, InvitationStatus.REVOKED):
            raise _not_pending(invitation)
        if status == InvitationStatus.EXPIRED:
            # An expired invite does not hold a seat; reviving it takes one.
            Organization.objects.select_for_update().filter(pk=invitation.organization_id).first()
            billing_services.ensure_seat_quota(invitation.organization)
        invitation.token_hash = digest
        invitation.expires_at = _new_expiry()
        invitation.save(update_fields=["token_hash", "expires_at", "updated_at"])
        _email_after_commit(invitation.pk, raw)
    return IssuedInvitation(invitation=invitation, raw_token=raw)


def revoke_invitation(invitation: Invitation) -> Invitation:
    with transaction.atomic():
        invitation = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if invitation.status != InvitationStatus.PENDING:
            raise _not_pending(invitation)
        invitation.revoked_at = timezone.now()
        invitation.save(update_fields=["revoked_at", "updated_at"])
    return invitation


def get_invitation_by_token(raw_token: str) -> Invitation:
    invitation = (
        Invitation.objects.select_related("organization", "invited_by")
        .filter(token_hash=hash_invitation_token(raw_token))
        .first()
    )
    if invitation is None:
        raise exceptions.NotFound("This invitation link is not valid.")
    return invitation


def account_exists(email: str) -> bool:
    return User.objects.filter(email=normalize_email(email)).exists()


def accept_invitation(
    *, raw_token: str, user: User | None, full_name: str = "", password: str = ""
) -> Membership:
    """Signed in mode when user is given (emails must match), otherwise create the
    account with the invited email."""
    with transaction.atomic():
        invitation = (
            Invitation.objects.select_for_update(of=("self",))
            .select_related("organization")
            .filter(token_hash=hash_invitation_token(raw_token))
            .first()
        )
        if invitation is None:
            raise exceptions.NotFound("This invitation link is not valid.")
        if invitation.status != InvitationStatus.PENDING:
            raise _not_pending(invitation)

        if user is not None:
            if normalize_email(user.email) != invitation.email:
                raise exceptions.PermissionDenied(
                    f"This invitation was sent to {invitation.email}. Sign in with that email to accept it.",
                    code="email_mismatch",
                )
            if Membership.objects.filter(organization=invitation.organization, user=user).exists():
                raise Conflict("You are already a member of this organization.", code="already_member")
        else:
            if account_exists(invitation.email):
                raise Conflict(
                    "An account with this email already exists. Sign in to accept the invitation.",
                    code="account_exists",
                )
            errors = password_errors(password, email=invitation.email, full_name=full_name)
            if errors:
                raise exceptions.ValidationError({"password": errors})
            user = User.objects.create_user(
                email=invitation.email, password=password, full_name=full_name.strip()
            )

        membership = Membership.objects.create(
            organization=invitation.organization, user=user, role=invitation.role
        )
        invitation.accepted_at = timezone.now()
        invitation.accepted_by = user
        invitation.save(update_fields=["accepted_at", "accepted_by", "updated_at"])
        return membership


def _email_after_commit(invitation_id: UUID, raw_token: str) -> None:
    # After commit, so an email never points at an invitation that was rolled back.
    transaction.on_commit(lambda: send_invitation_email(invitation_id, raw_token))


def send_invitation_email(invitation_id: UUID, raw_token: str) -> None:
    invitation = Invitation.objects.select_related("organization", "invited_by").get(pk=invitation_id)
    inviter = invitation.invited_by
    inviter_name = (inviter.full_name or inviter.email) if inviter else "A teammate"
    organization = invitation.organization.name
    expires = invitation.expires_at.strftime("%d %B %Y")
    role = invitation.get_role_display()
    body = (
        f"{inviter_name} invited you to join {organization} on Helploom as {role}.\n\n"
        f"Accept the invitation:\n{invite_url(raw_token)}\n\n"
        f"The link expires on {expires} (UTC). If you were not expecting this email, you can ignore it.\n"
    )
    try:
        send_mail(
            subject=f"Join {organization} on Helploom",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[invitation.email],
        )
    except Exception:
        # The invitation stays valid; the admin can resend once email works again.
        logger.exception("Could not send invitation %s", invitation_id)
