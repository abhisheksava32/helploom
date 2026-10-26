"""REST routes for accounts (auth/, invitations/, organization/). Contract: docs/API.md."""

from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("auth/signup/", views.SignupView.as_view(), name="signup"),
    path("auth/login/", views.LoginView.as_view(), name="login"),
    path("auth/refresh/", views.RefreshView.as_view(), name="refresh"),
    path("auth/logout/", views.LogoutView.as_view(), name="logout"),
    path("auth/me/", views.MeView.as_view(), name="me"),
    path("auth/password/", views.PasswordView.as_view(), name="password"),
    path("invitations/<str:token>/", views.PublicInvitationView.as_view(), name="invitation"),
    path("invitations/<str:token>/accept/", views.AcceptInvitationView.as_view(), name="invitation-accept"),
    path("organization/", views.OrganizationView.as_view(), name="organization"),
    path("organization/members/", views.MemberListView.as_view(), name="members"),
    path("organization/members/<uuid:pk>/", views.MemberDetailView.as_view(), name="member"),
    path("organization/invitations/", views.InvitationListView.as_view(), name="invitations"),
    path(
        "organization/invitations/<uuid:pk>/", views.InvitationDetailView.as_view(), name="invitation-detail"
    ),
    path(
        "organization/invitations/<uuid:pk>/resend/",
        views.InvitationResendView.as_view(),
        name="invitation-resend",
    ),
]
