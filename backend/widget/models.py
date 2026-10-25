"""Per organisation widget configuration and its public site key."""

from __future__ import annotations

import secrets

from django.contrib.postgres.fields import ArrayField
from django.core.validators import RegexValidator
from django.db import models

from core.models import TimeStampedModel

SITE_KEY_PREFIX = "hlp_pk_"

hex_color = RegexValidator(r"^#[0-9a-fA-F]{6}$", "Use a hex colour like #4f46e5.")


def generate_site_key() -> str:
    # Public by design (it ships in page source). Origin checks and rate limits, not
    # secrecy, are what protect the widget socket.
    return SITE_KEY_PREFIX + secrets.token_urlsafe(24)


class WidgetPosition(models.TextChoices):
    RIGHT = "right", "Bottom right"
    LEFT = "left", "Bottom left"


class WidgetConfig(TimeStampedModel):
    organization = models.OneToOneField(
        "accounts.Organization", on_delete=models.CASCADE, related_name="widget"
    )
    site_key = models.CharField(max_length=64, unique=True, default=generate_site_key)
    is_enabled = models.BooleanField(default=True)
    allowed_origins = ArrayField(
        models.CharField(max_length=255),
        default=list,
        blank=True,
        help_text='Exact origins such as "https://shop.example.com".',
    )
    title = models.CharField(max_length=60, default="Help")
    greeting = models.CharField(
        max_length=300, default="Hi! Ask me anything about our products and policies."
    )
    brand_color = models.CharField(max_length=7, default="#4f46e5", validators=[hex_color])
    position = models.CharField(max_length=5, choices=WidgetPosition.choices, default=WidgetPosition.RIGHT)

    def __str__(self) -> str:
        return f"Widget for {self.organization_id}"
