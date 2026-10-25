"""Account business logic. Owner: backend-core.

Planned entry points (views stay thin and call these):

    signup(email, password, full_name, organization_name) -> Membership
        Creates the user, the organisation, the owner membership, a Free
        billing.Subscription and a widget.WidgetConfig in one transaction.
    issue_tokens(user) -> TokenPair
    invite(organization, email, role, invited_by) -> Invitation
        Calls billing.services.ensure_seat_quota first, then emails the link
        FRONTEND_URL/invite/<token> with the configured email backend.
    accept_invitation(raw_token, user | None, full_name, password) -> Membership
    change_role(membership, role, actor) / remove_member(membership, actor)
        Never leave an organisation without an owner.
"""
