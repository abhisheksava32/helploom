"""Celery entry point for ingestion.

core.background.run_in_background calls .delay() on this task when CELERY_BROKER_URL
is set and calls it directly in the thread pool otherwise, so the same function runs
in both setups. acks_late makes the broker redeliver a job whose worker died, which is
the production answer to "the document stayed queued forever".
"""

from __future__ import annotations

from celery import shared_task

from .models import IngestionTrigger


@shared_task(name="knowledge.ingest_document", acks_late=True, ignore_result=True)
def ingest_document_task(document_id: str, trigger: str = IngestionTrigger.UPLOAD) -> None:
    from .services import ingest_document

    ingest_document(document_id, trigger)
