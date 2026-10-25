"""Identity and tenancy: users, organisations (workspaces), memberships and invitations."""

from __future__ import annotations

import hashlib
import secrets
from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models
from django.db.models import Q
from django.db.models.functions import Lower
from django.utils import timezone

from core.models import OrganizationQuerySet, TimeStampedModel, UUIDModel


class Role(models.TextChoices):
    OWNER = "owner", "Owner"
    ADMIN = "admin", "Admin"
    AGENT = "agent", "Agent"


class Tone(models.TextChoices):
    FRIENDLY = "friendly", "Friendly"
    PROFESSIONAL = "professional", "Professional"
    CONCISE = "concise", "Concise"


def normalize_email(email: str) -> str:
    # Lower casing the whole address is technically stricter than RFC 5321, but it is
    # what users expect from a login form and it keeps uniqueness simple.
    return email.strip().lower()


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, email: str, password: str | None = None, **extra: Any) -> User:
        if not email:
            raise ValueError("Users need an email address.")
        user = self.model(email=normalize_email(email), **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email: str, password: str | None = None, **extra: Any) -> User:
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        return self.create_user(email, password, **extra)


class User(UUIDModel, AbstractBaseUser, PermissionsMixin):
    """Email based login. A user can belong to several organisations via Membership."""

    email = models.EmailField(unique=True)
    full_name = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = "email"
    EMAIL_FIELD = "email"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ["email"]
        constraints = [
            models.UniqueConstraint(Lower("email"), name="accounts_user_email_ci_unique"),
        ]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.email


class Organization(TimeStampedModel):
    """A workspace. Every tenant owned row points here."""

    name = models.CharField(max_length=150)
    slug = models.SlugField(max_length=60, unique=True)
    assistant_tone = models.CharField(max_length=20, choices=Tone.choices, default=Tone.FRIENDLY)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Membership(TimeStampedModel):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="memberships")
    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="memberships")
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["created_at"]
        constraints = [
            models.UniqueConstraint(fields=["user", "organization"], name="accounts_membership_unique"),
        ]

    def __str__(self) -> str:
        return f"{self.user} in {self.organization} as {self.role}"


def hash_invitation_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode()).hexdigest()


class InvitationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    ACCEPTED = "accepted", "Accepted"
    REVOKED = "revoked", "Revoked"
    EXPIRED = "expired", "Expired"


class Invitation(TimeStampedModel):
    """An emailed invite link. Only a hash of the token is stored, so a database leak
    does not hand out working invite links."""

    organization = models.ForeignKey(Organization, on_delete=models.CASCADE, related_name="invitations")
    email = models.EmailField()
    role = models.CharField(max_length=10, choices=Role.choices, default=Role.AGENT)
    token_hash = models.CharField(max_length=64, unique=True)
    invited_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    expires_at = models.DateTimeField()
    accepted_at = models.DateTimeField(null=True, blank=True)
    accepted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+")
    revoked_at = models.DateTimeField(null=True, blank=True)

    objects = OrganizationQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "email"],
                condition=Q(accepted_at__isnull=True, revoked_at__isnull=True),
                name="accounts_invitation_one_pending_per_email",
            ),
        ]

    @staticmethod
    def new_token() -> tuple[str, str]:
        """Return (raw token for the email link, hash to store)."""
        raw = secrets.token_urlsafe(32)
        return raw, hash_invitation_token(raw)

    @property
    def status(self) -> str:
        if self.accepted_at:
            return InvitationStatus.ACCEPTED
        if self.revoked_at:
            return InvitationStatus.REVOKED
        if self.expires_at <= timezone.now():
            return InvitationStatus.EXPIRED
        return InvitationStatus.PENDING

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email = normalize_email(self.email)
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Invite {self.email} to {self.organization}"
