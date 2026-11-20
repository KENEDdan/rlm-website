"""DEMO ONLY: ``manage.py seed_indicators --demo`` creates clearly fake sample targets (ministry decision 4).

Real targets are set by leadership on the Performance targets screen or imported from a CSV file. These samples
exist only to show the screens working: every name starts with "[DEMO]", every row is flagged ``is_demo`` and
shows a "Demo" badge, and ``--remove`` deletes them all (with their actuals). Without ``--demo`` nothing happens.
Idempotent.
"""

from __future__ import annotations

import datetime as dt
from decimal import Decimal
from typing import Any

from django.core.management.base import BaseCommand, CommandParser
from django.utils import timezone

from portal.indicators import ensure_monthly
from portal.models import Department, Indicator, IndicatorValue

PREFIX = "[DEMO] "

# department: [(category, name, unit, annual target, higher_is_better, auto_source)]
SUGGESTED: dict[str, list[tuple[str, str, str, int, bool, str]]] = {
    "membership": [
        ("membership", "New members", "number", 120, True, "new_in_period"),
        ("membership", "Applications waiting", "number", 0, False, "pending_approvals"),
    ],
    "finance": [
        ("finance", "Income", "money", 60000, True, "income"),
        ("partnerships", "New partners", "number", 24, True, ""),
    ],
    "logistics": [("development", "Late deliveries", "number", 0, False, "late_deliveries")],
    "media": [("media", "Social reach", "number", 60000, True, "social_reach")],
    "missions": [
        ("evangelism", "Decisions for Christ", "number", 600, True, "decisions"),
        ("missions", "People reached", "number", 12000, True, "people_reached"),
        ("missions", "Follow-up completion", "percent", 60, True, "follow_up_rate"),
    ],
    "discipleship": [
        ("discipleship", "People enrolled in classes", "number", 600, True, "enrolled"),
        ("youth", "Youth fellowship attendance", "number", 2400, True, ""),
        ("prayer", "Prayer meetings held", "number", 48, True, ""),
    ],
    "development": [("development", "Maintenance backlog", "number", 36, False, "maintenance_backlog")],
}


class Command(BaseCommand):
    help = "DEMO ONLY: create clearly fake sample targets (--demo) or remove them (--remove)."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument("--demo", action="store_true", help="Create the fake sample targets and actuals.")
        parser.add_argument("--remove", action="store_true", help="Delete every demo target and its actuals.")

    def handle(self, *args: Any, **options: Any) -> None:
        if options["remove"]:
            count = Indicator.objects.filter(is_demo=True).delete()[0]
            self.stdout.write(self.style.SUCCESS(f"Removed {count} demo row(s)."))
            return
        if not options["demo"]:
            self.stdout.write(
                "Nothing done. Real targets are set by leadership under Performance targets (or imported from "
                "CSV). Use --demo to create clearly fake sample targets for a demonstration."
            )
            return
        today = timezone.localdate()
        created = 0
        for code, rows in SUGGESTED.items():
            department = Department.objects.get(code=code)
            for category, name, unit, annual, higher, source in rows:
                indicator, made = Indicator.objects.get_or_create(
                    department=department,
                    name=PREFIX + name,
                    year=today.year,
                    branch=None,
                    defaults={
                        "category": category,
                        "unit": unit,
                        "annual_target": Decimal(annual),
                        "higher_is_better": higher,
                        "auto_source": source,
                        "is_demo": True,
                        "description": "Fake sample target for demonstration only.",
                    },
                )
                created += made
                ensure_monthly(indicator)
                targets = indicator.monthly_map()
                for month in range(1, today.month):  # fake actuals around the target, last month left empty
                    if month == today.month - 1 and month % 2:
                        continue  # leave one overdue month to show the flag
                    factor = Decimal(("0.6", "0.8", "0.95", "1.1")[month % 4])
                    IndicatorValue.objects.get_or_create(
                        indicator=indicator,
                        period_start=dt.date(today.year, month, 1),
                        defaults={
                            "value": (targets[month] * factor).quantize(Decimal("1")),
                            "note": "Demo figure",
                        },
                    )
        self.stdout.write(self.style.SUCCESS(f"{created} demo target(s) created (names start with [DEMO])."))
