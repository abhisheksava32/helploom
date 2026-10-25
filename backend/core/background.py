"""Run work off the request path: Celery when a broker is configured, else a thread pool.

Callers do not care which one runs the job:

    run_in_background(ingest_document, str(document.id))

Pass a Celery task (anything with .delay) to use the broker when CELERY_BROKER_URL is
set; it is called directly in the thread pool otherwise. Jobs are queued after the
current transaction commits so a worker never reads rows that do not exist yet.
Arguments must be JSON friendly (ids, not model instances) so both paths behave alike.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from django.conf import settings
from django.db import close_old_connections, connections, transaction

logger = logging.getLogger(__name__)

_executor: ThreadPoolExecutor | None = None
_executor_lock = threading.Lock()


def _get_executor() -> ThreadPoolExecutor:
    global _executor
    with _executor_lock:
        if _executor is None:
            _executor = ThreadPoolExecutor(
                max_workers=settings.INGESTION_MAX_WORKERS,
                thread_name_prefix="helploom-job",
            )
        return _executor


def _run_job(func: Callable[..., Any], args: tuple[Any, ...]) -> None:
    close_old_connections()
    try:
        func(*args)
    except Exception:
        logger.exception("Background job %s failed", getattr(func, "__name__", func))
    finally:
        # Each pool thread holds its own connection; release it between jobs.
        connections.close_all()


def run_in_background(func: Callable[..., Any], *args: Any) -> None:
    if settings.BACKGROUND_TASKS_EAGER:
        func(*args)
        return

    delay = getattr(func, "delay", None)
    if settings.CELERY_BROKER_URL and callable(delay):
        transaction.on_commit(lambda: delay(*args))
        return

    transaction.on_commit(lambda: _get_executor().submit(_run_job, func, args))
