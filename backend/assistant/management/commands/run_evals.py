"""Run the retrieval and answer evaluation on the sample knowledge base.

    uv run python manage.py run_evals                  # all retrieval modes + answers
    uv run python manage.py run_evals --sweep          # also sweep the relevance threshold
    uv run python manage.py run_evals --provider claude --embedder ollama
    uv run python manage.py run_evals --json evals.json --verbose

Nothing is written to the database: the sample organisation lives in a transaction
that is rolled back at the end.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.test import override_settings

from evals.runner import MODES, format_report, run


class Command(BaseCommand):
    help = "Evaluate retrieval and answers on the sample knowledge base in evals/kb/."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--mode", choices=[*MODES, "all"], default="all", help="Retrieval mode to measure."
        )
        parser.add_argument("-k", type=int, default=5, help="Cutoff for hit rate (default 5).")
        parser.add_argument("--sweep", action="store_true", help="Sweep the relevance threshold.")
        parser.add_argument("--no-answers", action="store_true", help="Measure retrieval only.")
        parser.add_argument(
            "--provider", choices=["auto", "ollama", "claude", "extractive"], help="Override LLM_PROVIDER."
        )
        parser.add_argument("--embedder", choices=["auto", "ollama", "hashing"], help="Override EMBEDDER.")
        parser.add_argument(
            "--json", dest="json_path", help="Also write the full report as JSON to this file."
        )
        parser.add_argument("--verbose", action="store_true", help="Print every case.")

    def handle(self, *args: Any, **options: Any) -> None:
        overrides: dict[str, Any] = {}
        if options["provider"]:
            overrides["LLM_PROVIDER"] = options["provider"]
        if options["embedder"]:
            overrides["EMBEDDER"] = options["embedder"]
        modes = MODES if options["mode"] == "all" else (options["mode"],)
        with override_settings(**overrides):
            report = run(
                modes=modes, k=options["k"], answers=not options["no_answers"], sweep=options["sweep"]
            )
        self.stdout.write(format_report(report, verbose=options["verbose"]))
        if options["json_path"]:
            Path(options["json_path"]).write_text(json.dumps(report.as_dict(), indent=2, default=str))
            self.stdout.write(f"\nWrote {options['json_path']}")
