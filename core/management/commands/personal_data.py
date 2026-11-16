"""Answer a data-subject request: ``personal_data export|erase --email someone@example.org``."""

from __future__ import annotations

import getpass
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.privacy import erase_person, export_person, find_person


class Command(BaseCommand):
    help = "Export or erase all personal data held for one email address (audit-logged)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("action", choices=["find", "export", "erase"])
        parser.add_argument("--email", required=True)
        parser.add_argument("--output", help="Write the export to this file instead of stdout.")
        parser.add_argument("--yes", action="store_true", help="Confirm erasure (cannot be undone).")

    def handle(self, *args: Any, action: str, email: str, **options: Any) -> None:
        actor = f"manage.py:{getpass.getuser()}"
        if action == "find":
            for label, qs in find_person(email).items():
                self.stdout.write(f"{label}: {qs.count()}")
            return
        if action == "export":
            document = export_person(email, actor=actor)
            if options.get("output"):
                with open(options["output"], "w", encoding="utf-8") as fh:
                    fh.write(document)
                self.stdout.write(
                    self.style.SUCCESS(f"Written to {options['output']}. Delete it after sending.")
                )
            else:
                self.stdout.write(document)
            return
        if not options.get("yes"):
            raise CommandError("Erasure cannot be undone. Re-run with --yes to confirm.")
        for label, count in erase_person(email, actor=actor).items():
            self.stdout.write(f"{label}: {count}")
        self.stdout.write(self.style.SUCCESS("Erased. Donations were anonymised, not deleted."))
