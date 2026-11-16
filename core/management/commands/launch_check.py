"""Launch readiness report: ``manage.py launch_check [--all] [--strict]``."""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError

from core.launch import BLOCKER, OK, WARNING, run_checks


class Command(BaseCommand):
    help = "List what is still a placeholder or unsafe before the website goes public."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--all", action="store_true", help="Also list the checks that pass.")
        parser.add_argument(
            "--strict", action="store_true", help="Exit with an error if any BLOCKER remains."
        )

    def handle(self, *args: Any, **options: Any) -> None:
        results = run_checks()
        style = {BLOCKER: self.style.ERROR, WARNING: self.style.WARNING, OK: self.style.SUCCESS}
        for item in results:
            if item.level == OK and not options["all"]:
                continue
            self.stdout.write(style[item.level](f"[{item.level}] {item.area}: {item.message}"))
            if item.fix:
                self.stdout.write(f"          fix: {item.fix}")
        counts = {level: sum(1 for r in results if r.level == level) for level in (BLOCKER, WARNING, OK)}
        self.stdout.write(
            f"\n{counts[BLOCKER]} blocker(s), {counts[WARNING]} warning(s), {counts[OK]} check(s) passed."
        )
        if options["strict"] and counts[BLOCKER]:
            raise CommandError("Not ready to launch: fix the BLOCKER items above.")
