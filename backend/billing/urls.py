"""REST routes for billing (/api/v1/billing/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "billing"

urlpatterns = [
    path("plans/", views.PlanListView.as_view(), name="plans"),
    path("subscription/", views.SubscriptionView.as_view(), name="subscription"),
    path("checkout/", views.CheckoutView.as_view(), name="checkout"),
    path("portal/", views.PortalView.as_view(), name="portal"),
    path("webhook/", views.StripeWebhookView.as_view(), name="webhook"),
]
