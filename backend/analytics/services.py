"""Report queries. Owner: backend-core.

Every function takes the organisation and a date range and aggregates
assistant.Message, assistant.Conversation, assistant.Citation and
assistant.HandoffTicket with Model.objects.for_organization(org). Planned:

    overview(org, start, end)            conversations_per_day(org, start, end)
    top_questions(org, start, end, n)    top_documents(org, start, end, n)
    unanswered_questions(org, start, end) -> QuerySet (paginated by the view)
    cost_by_provider(org, start, end)
"""
