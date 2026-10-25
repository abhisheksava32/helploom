"""The tenant queryset that every tenant owned model uses."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from accounts.models import Membership


@pytest.mark.django_db
def test_for_organization_accepts_instances_and_ids(make_member: Callable[..., Membership]) -> None:
    mine = make_member()
    make_member()

    by_instance = Membership.objects.for_organization(mine.organization)
    by_id = Membership.objects.for_organization(str(mine.organization_id))

    assert list(by_instance) == [mine]
    assert list(by_id) == [mine]
