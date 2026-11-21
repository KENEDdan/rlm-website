"""Delete unsuccessful applications past their retention deadline (ministry decision 8).

``manage.py purge_applications --dry-run`` lists what would be deleted without deleting anything.
The same job runs nightly through Celery beat (``core.tasks.purge_unsuccessful_applications``).
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandParser

from core.retention import purge


class Command(BaseCommand):
    help = "Delete unsuccessful applications past their retention deadline (use --dry-run to preview)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Only list what would be deleted.")

    def handle(self, *args: Any, **options: Any) -> None:
        result = purge(dry_run=options["dry_run"])
        if options["dry_run"]:
            for c in result["candidates"]:
                self.stdout.write(f"would delete {c.reference} (deadline {c.deadline:%Y-%m-%d})")
            self.stdout.write(
                self.style.SUCCESS(f"Dry run: {len(result['candidates'])} due, nothing deleted.")
            )
            return
        self.stdout.write(self.style.SUCCESS(f"Deleted {result['deleted']}, skipped {result['skipped']}."))
