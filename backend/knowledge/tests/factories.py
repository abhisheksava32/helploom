"""Helpers for building documents in tests (fixtures live in conftest.py)."""

from __future__ import annotations

from typing import Any

from django.core.files.uploadedfile import SimpleUploadedFile

from accounts.models import Organization
from knowledge.models import Document
from knowledge.services import create_document, ingest_document

REFUND_POLICY = """# Refund policy

## Refund window

Customers can request a refund within 30 days of delivery. Refunds are issued to the
original payment method within 5 business days.

## Exchanges

Exchanges are free for unused items in their original packaging.
"""

SHIPPING_FAQ = """# Shipping FAQ

## Delivery times

Standard delivery takes 3 to 5 business days. Express delivery arrives the next
business day when ordered before noon.

## Order SKU-4471

The limited edition grinder SKU-4471 ships only within the United States.
"""


def ingest(organization: Organization, filename: str, content: str | bytes, **extra: Any) -> Document:
    """Store and ingest one document synchronously, as the background job would."""
    data = content.encode() if isinstance(content, str) else content
    document = create_document(organization, filename=filename, data=data, **extra)
    ingest_document(document.pk)
    document.refresh_from_db()
    return document


def upload(name: str, content: str | bytes) -> SimpleUploadedFile:
    data = content.encode() if isinstance(content, str) else content
    # The browser supplied type is deliberately wrong: the server must not trust it.
    return SimpleUploadedFile(name, data, content_type="application/octet-stream")
