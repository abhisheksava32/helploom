"""Smoke tests for the HTTP stack: routing, the database, pgvector and the error format."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_health_reports_database_and_pgvector(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/health/")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": "0.1.0", "database": "ok", "pgvector": True}


@pytest.mark.django_db
def test_unknown_api_path_uses_the_error_format(api_client: APIClient) -> None:
    response = api_client.get("/api/v1/does-not-exist/")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "not_found", "message": "No endpoint matches this URL.", "details": {}}
    }


@pytest.mark.django_db
def test_wrong_method_uses_the_error_format(api_client: APIClient) -> None:
    response = api_client.post("/api/v1/health/", {})

    assert response.status_code == 405
    body = response.json()
    assert body["error"]["code"] == "method_not_allowed"
    assert body["error"]["details"] == {}


@pytest.mark.django_db
def test_cors_allows_the_dashboard_origin_only(api_client: APIClient) -> None:
    allowed = api_client.options(
        "/api/v1/health/",
        HTTP_ORIGIN="http://localhost:3000",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )
    blocked = api_client.options(
        "/api/v1/health/",
        HTTP_ORIGIN="https://evil.example",
        HTTP_ACCESS_CONTROL_REQUEST_METHOD="GET",
    )

    assert allowed["access-control-allow-origin"] == "http://localhost:3000"
    assert "access-control-allow-origin" not in blocked
