"""List filtering helpers shared by the dashboard endpoints."""

from __future__ import annotations

from typing import Any

from rest_framework.filters import OrderingFilter


class AliasOrderingFilter(OrderingFilter):
    """?ordering= with public names that map to annotations or related fields.

    A view lists the public names in ordering_fields and maps the ones that are not
    plain columns in ordering_aliases, for example {"email": "user__email"}. Unknown
    names are dropped and the view's default ordering applies, as docs/API.md says.
    A primary key tie breaker keeps pagination stable when values repeat.
    """

    def get_ordering(self, request: Any, queryset: Any, view: Any) -> list[str]:
        ordering = list(super().get_ordering(request, queryset, view) or [])
        aliases: dict[str, str] = getattr(view, "ordering_aliases", {})
        resolved = []
        for term in ordering:
            descending = term.startswith("-")
            name = aliases.get(term.lstrip("-"), term.lstrip("-"))
            resolved.append(f"-{name}" if descending else name)
        if resolved and not any(term.lstrip("-") in {"pk", "id"} for term in resolved):
            resolved.append("pk")
        return resolved
