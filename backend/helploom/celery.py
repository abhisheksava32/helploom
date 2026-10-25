"""Celery application, used only when CELERY_BROKER_URL is set.

Without a broker, background jobs run in the in-process thread pool from
core.background, so local development needs no Redis.
"""

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "helploom.settings")

app = Celery("helploom")
app.config_from_object("django.conf:settings", namespace="CELERY")
# Finds tasks.py in every installed app (knowledge.tasks holds ingestion).
app.autodiscover_tasks()
