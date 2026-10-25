"""Unit tests for the shared building blocks in core."""

from __future__ import annotations

from typing import Any

import pytest
from django.core.cache import cache
from rest_framework import exceptions

from core import ratelimit, services
from core.exceptions import PlanLimitExceeded, exception_handler
from core.origins import normalize_origin, origin_allowed
from core.permissions import has_role


@pytest.mark.django_db
def test_health_report_sees_the_vector_extension() -> None:
    assert services.health_report()["pgvector"] is True


def _handle(exc: Exception) -> tuple[int, dict[str, Any]]:
    response = exception_handler(exc, {"view": None})
    return response.status_code, response.data


def test_validation_errors_keep_field_details() -> None:
    status, body = _handle(exceptions.ValidationError({"email": ["Enter a valid email address."]}))

    assert status == 400
    assert body == {
        "error": {
            "code": "validation_error",
            "message": "Enter a valid email address.",
            "details": {"email": ["Enter a valid email address."]},
        }
    }


def test_plan_limit_errors_carry_usage_details() -> None:
    exc = PlanLimitExceeded("Over the limit.", limit="documents", used=10, allowed=10, plan="free")

    status, body = _handle(exc)

    assert status == 402
    assert body["error"]["code"] == "plan_limit_exceeded"
    assert body["error"]["details"] == {"limit": "documents", "used": 10, "allowed": 10, "plan": "free"}


def test_throttled_errors_report_retry_after() -> None:
    status, body = _handle(exceptions.Throttled(wait=4.2))

    assert status == 429
    assert body["error"]["code"] == "throttled"
    assert body["error"]["details"]["retry_after"] == 5


def test_permission_codes_pass_through() -> None:
    status, body = _handle(exceptions.PermissionDenied("Nope.", code="insufficient_role"))

    assert status == 403
    assert body["error"] == {"code": "insufficient_role", "message": "Nope.", "details": {}}


def test_unexpected_errors_become_a_generic_500() -> None:
    status, body = _handle(RuntimeError("database password is hunter2"))

    assert status == 500
    assert body["error"]["code"] == "server_error"
    assert "hunter2" not in body["error"]["message"]


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("https://Shop.Example.com", "https://shop.example.com"),
        ("https://shop.example.com:443", "https://shop.example.com"),
        ("http://localhost:3000/", "http://localhost:3000"),
        ("https://shop.example.com/path", None),
        ("ftp://shop.example.com", None),
        ("", None),
    ],
)
def test_normalize_origin(raw: str, expected: str | None) -> None:
    assert normalize_origin(raw) == expected


def test_origin_allowed_compares_normalised_values() -> None:
    assert origin_allowed("https://shop.example.com", ["https://SHOP.example.com:443"])
    assert not origin_allowed("https://shop.example.com.evil.test", ["https://shop.example.com"])


def test_rate_limit_blocks_after_the_limit() -> None:
    cache.clear()
    results = [ratelimit.hit("test:ip", limit=2, window_seconds=60) for _ in range(3)]

    assert [r.allowed for r in results] == [True, True, False]
    assert results[-1].remaining == 0


def test_hash_ip_is_stable_and_not_the_raw_ip() -> None:
    assert ratelimit.hash_ip("203.0.113.9") == ratelimit.hash_ip("203.0.113.9")
    assert "203.0.113.9" not in ratelimit.hash_ip("203.0.113.9")


@pytest.mark.parametrize(
    ("role", "minimum", "allowed"),
    [
        ("owner", "admin", True),
        ("admin", "admin", True),
        ("agent", "admin", False),
        ("admin", "owner", False),
    ],
)
def test_role_ranking(role: str, minimum: str, allowed: bool) -> None:
    assert has_role(role, minimum) is allowed
