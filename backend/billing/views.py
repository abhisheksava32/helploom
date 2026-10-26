"""Plans, subscription, checkout, portal and the Stripe webhook (docs/API.md, section 11)."""

from __future__ import annotations

from typing import Any

from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.tenancy import OrganizationScopedMixin

from . import services
from .serializers import CheckoutSerializer, PlanSerializer


class PlanListView(APIView):
    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]

    def get(self, request: Request) -> Response:
        return Response({"results": PlanSerializer(services.list_plans(), many=True).data})


class SubscriptionView(OrganizationScopedMixin, APIView):
    read_role = "agent"

    def get(self, request: Request) -> Response:
        return Response(services.subscription_payload(services.get_subscription(self.organization.id)))


class CheckoutView(OrganizationScopedMixin, APIView):
    write_role = "owner"

    def post(self, request: Request) -> Response:
        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = services.start_checkout(
            self.organization, serializer.validated_data["plan"], customer_email=self.membership.user.email
        )
        return Response(
            {
                "mode": result.mode,
                "checkout_url": result.checkout_url,
                "subscription": services.subscription_payload(result.subscription),
            }
        )


class PortalView(OrganizationScopedMixin, APIView):
    write_role = "owner"

    def post(self, request: Request) -> Response:
        return Response({"url": services.billing_portal_url(self.organization)})


class StripeWebhookView(APIView):
    """Authenticated by the Stripe-Signature header over the raw body, so the body is
    read as bytes and never parsed by DRF first."""

    authentication_classes: list[Any] = []
    permission_classes = [AllowAny]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "webhook"

    def post(self, request: Request) -> Response:
        services.handle_stripe_webhook(request.body, request.headers.get("Stripe-Signature"))
        return Response({"received": True})
