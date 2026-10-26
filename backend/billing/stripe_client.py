"""The only module that talks to Stripe. Used only when STRIPE_SECRET_KEY is set.

Keeping the SDK behind three small functions means billing.services works with plain
values, tests replace these functions instead of the network, and an SDK upgrade
touches one file.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import stripe
from django.conf import settings
from rest_framework import status

from core.exceptions import HelploomError, ServiceUnavailable

logger = logging.getLogger(__name__)

WEBHOOK_TOLERANCE_SECONDS = 300


class InvalidSignature(HelploomError):
    status_code = status.HTTP_400_BAD_REQUEST
    default_code = "invalid_signature"
    default_detail = "The webhook signature could not be verified."


def is_configured() -> bool:
    return bool(settings.STRIPE_SECRET_KEY)


def _client() -> stripe.StripeClient:
    return stripe.StripeClient(settings.STRIPE_SECRET_KEY, max_network_retries=2)


def _unavailable(exc: stripe.StripeError) -> ServiceUnavailable:
    # The SDK message can include request ids and parameter names; log it, show a
    # plain sentence instead.
    logger.warning("Stripe request failed: %s", exc.user_message or type(exc).__name__)
    return ServiceUnavailable("Billing is temporarily unavailable. Please try again in a minute.")


def create_checkout_session(
    *,
    organization_id: str,
    plan_code: str,
    price_id: str,
    customer_id: str,
    customer_email: str,
    success_url: str,
    cancel_url: str,
) -> str:
    """Start a subscription Checkout and return the hosted page URL."""
    metadata = {"organization_id": organization_id, "plan": plan_code}
    params: dict[str, Any] = {
        "mode": "subscription",
        "line_items": [{"price": price_id, "quantity": 1}],
        "success_url": success_url,
        "cancel_url": cancel_url,
        # Lets the webhook find the organisation even before we know the customer id.
        "client_reference_id": organization_id,
        "metadata": metadata,
        "subscription_data": {"metadata": metadata},
    }
    if customer_id:
        params["customer"] = customer_id
    elif customer_email:
        params["customer_email"] = customer_email
    try:
        session = _client().v1.checkout.sessions.create(params=params)  # type: ignore[arg-type]
    except stripe.StripeError as exc:
        raise _unavailable(exc) from exc
    return str(session.url)


def create_portal_session(*, customer_id: str, return_url: str) -> str:
    try:
        session = _client().v1.billing_portal.sessions.create(
            params={"customer": customer_id, "return_url": return_url}
        )
    except stripe.StripeError as exc:
        raise _unavailable(exc) from exc
    return str(session.url)


def verify_webhook(payload: bytes, signature: str | None) -> dict[str, Any]:
    """Check the Stripe-Signature header and return the event as a plain dict."""
    secret = settings.STRIPE_WEBHOOK_SECRET
    if not secret or not signature:
        raise InvalidSignature()
    try:
        text = payload.decode("utf-8")
        stripe.WebhookSignature.verify_header(text, signature, secret, tolerance=WEBHOOK_TOLERANCE_SECONDS)
        event = json.loads(text)
    except (stripe.SignatureVerificationError, UnicodeDecodeError, ValueError) as exc:
        raise InvalidSignature() from exc
    if not isinstance(event, dict) or not isinstance(event.get("id"), str):
        raise InvalidSignature()
    return event
