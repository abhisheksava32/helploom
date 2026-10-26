"""Re-embed ready documents with the active embedder.

Run after switching EMBEDDER (or after Ollama becomes available in auto mode). Only
documents embedded by a different embedder are touched unless --all is given; chunk
text is reused, so files are not extracted again.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from knowledge.embeddings import get_embedder
from knowledge.services import reembed_documents


class Command(BaseCommand):
    help = "Re-embed stored chunks with the active embedder."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--organization", help="Only this organisation id.")
        parser.add_argument("--all", action="store_true", help="Re-embed even documents already up to date.")

    def handle(self, *args: Any, **options: Any) -> None:
        embedder = get_embedder()
        self.stdout.write(f"Active embedder: {embedder.name}")
        report = reembed_documents(
            organization_id=options.get("organization"), force=options["all"], embedder=embedder
        )
        self.stdout.write(
            self.style.SUCCESS(f"Re-embedded {report.documents} documents ({report.chunks} chunks).")
        )
        if report.failed:
            self.stderr.write(f"{len(report.failed)} documents failed: {', '.join(report.failed)}")
