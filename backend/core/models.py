"""Abstract base models and the tenant aware queryset shared by every app."""

from __future__ import annotations

import uuid
from typing import Any, Self

from django.db import models


class UUIDModel(models.Model):
    """UUID primary keys keep ids unguessable in URLs and safe to expose to clients."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class TimeStampedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class OrganizationQuerySet(models.QuerySet):
    """Manager for tenant owned rows: Document.objects.for_organization(org).

    Every query outside a tenant scoped view goes through this, so the organisation
    filter is spelled the same way everywhere and is easy to audit.
    """

    def for_organization(self, organization: Any) -> Self:
        organization_id = getattr(organization, "pk", organization)
        return self.filter(organization_id=organization_id)
