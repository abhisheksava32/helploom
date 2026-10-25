"""Widget configuration defaults and validation."""

from __future__ import annotations

from collections.abc import Callable

import pytest
from django.core.exceptions import ValidationError

from accounts.models import Organization
from widget.models import SITE_KEY_PREFIX, WidgetConfig


@pytest.mark.django_db
def test_site_keys_are_prefixed_and_unique(
    organization: Organization, make_organization: Callable[..., Organization]
) -> None:
    first = WidgetConfig.objects.create(organization=organization)
    second = WidgetConfig.objects.create(organization=make_organization())

    assert first.site_key.startswith(SITE_KEY_PREFIX)
    assert first.site_key != second.site_key


@pytest.mark.django_db
def test_brand_colour_must_be_a_hex_value(organization: Organization) -> None:
    widget = WidgetConfig(organization=organization, brand_color="purple")

    with pytest.raises(ValidationError):
        widget.full_clean()
