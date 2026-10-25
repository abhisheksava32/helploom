"""Platform level checks used by the health endpoint and the provider status panel."""

from __future__ import annotations

from typing import TypedDict

from django.conf import settings
from django.db import connection


class HealthReport(TypedDict):
    status: str
    version: str
    database: str
    pgvector: bool


def health_report() -> HealthReport:
    """One database round trip that also proves the vector extension is installed."""
    database = "ok"
    vector = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1 FROM pg_extension WHERE extname = 'vector'")
            vector = cursor.fetchone() is not None
    except Exception:
        database = "unavailable"
    healthy = database == "ok" and vector
    return {
        "status": "ok" if healthy else "degraded",
        "version": settings.HELPLOOM_VERSION,
        "database": database,
        "pgvector": vector,
    }
