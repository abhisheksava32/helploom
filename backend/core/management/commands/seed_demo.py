"""uv run python manage.py seed_demo [--reset] [--password ...]

Creates the demo workspace described in core/demo.py and prints how to sign in.
"""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError, CommandParser

from core import demo


class Command(BaseCommand):
    help = "Create a demo user, workspace, sample documents and example conversations."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--reset", action="store_true", help="Delete an existing demo workspace and build it again."
        )
        parser.add_argument("--password", help="Password for the demo user (default: a random one).")

    def handle(self, *args: Any, **options: Any) -> None:
        try:
            summary = demo.seed_demo(
                password=options["password"],
                reset=options["reset"],
                log=lambda line: self.stdout.write(f"  {line}"),
            )
        except demo.DemoExists as exc:
            raise CommandError(str(exc)) from exc
        except ValueError as exc:
            raise CommandError(f"Choose another password: {exc}") from exc

        answers = ", ".join(f"{count} {kind}" for kind, count in sorted(summary.answer_types.items()))
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("Demo workspace ready."))
        self.stdout.write(f"  Sign in at  {settings.FRONTEND_URL}/login")
        self.stdout.write(f"  Email       {summary.email}")
        self.stdout.write(f"  Password    {summary.password}")
        self.stdout.write(f"  Site key    {summary.site_key}")
        self.stdout.write(f"  Documents   {summary.documents}")
        self.stdout.write(f"  Answers     {answers}")
