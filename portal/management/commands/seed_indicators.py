"""Create SUGGESTED M&E indicators for every department: ``manage.py seed_indicators``.

Targets are placeholders for leadership to change (Targets screen of each department). Each indicator is linked
to a dashboard figure (``auto_source``) so generating the monthly report fills the value in automatically.
Idempotent: existing indicators (matched by department + name) are never changed.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from portal.models import Department, Indicator

# department: [(name, unit, target, higher_is_better, auto_source, description)]
SUGGESTED: dict[str, list[tuple[str, str, int, bool, str, str]]] = {
    "membership": [
        ("Active members", "number", 200, True, "active_members", "Members with status Active at month end."),
        ("New members per month", "number", 10, True, "new_in_period", "Members who joined in the month."),
        ("Applications waiting", "number", 0, False, "pending_approvals", "Applications not yet decided."),
    ],
    "finance": [
        ("Income per month", "money", 5000, True, "income", "Posted income in the month."),
        (
            "Entries awaiting approval",
            "number",
            0,
            False,
            "awaiting_approval",
            "Recorded but not yet approved.",
        ),
    ],
    "logistics": [
        (
            "Late deliveries",
            "number",
            0,
            False,
            "late_deliveries",
            "Orders past their expected delivery date.",
        ),
        (
            "Purchases awaiting approval",
            "number",
            0,
            False,
            "pending_approvals",
            "Budget confirmed, not approved.",
        ),
    ],
    "media": [
        ("Events without a coverage plan", "number", 0, False, "events_uncovered", "Next 30 days."),
        (
            "Social reach per month",
            "number",
            5000,
            True,
            "social_reach",
            "Entered by hand from platform insights.",
        ),
    ],
    "missions": [
        ("Decisions for Christ per month", "number", 50, True, "decisions", "From field reports."),
        ("People reached per month", "number", 1000, True, "people_reached", "From field reports."),
        (
            "Follow-up completion",
            "percent",
            60,
            True,
            "follow_up_rate",
            "Converts enrolled in discipleship or beyond.",
        ),
    ],
    "discipleship": [
        ("People enrolled", "number", 50, True, "enrolled", "Currently enrolled in a class."),
        (
            "Converts awaiting follow-up",
            "number",
            0,
            False,
            "awaiting_follow_up",
            "Handed over, not yet visited.",
        ),
    ],
    "development": [
        ("Milestones overdue", "number", 0, False, "milestones_overdue", "Across active projects."),
        ("Maintenance backlog", "number", 3, False, "maintenance_backlog", "Open maintenance requests."),
    ],
}


class Command(BaseCommand):
    help = "Create suggested M&E indicators per department (placeholders; existing ones are left alone)."

    def handle(self, *args: Any, **options: Any) -> None:
        created = 0
        for code, rows in SUGGESTED.items():
            department = Department.objects.get(code=code)
            for name, unit, target, higher, source, description in rows:
                _obj, made = Indicator.objects.get_or_create(
                    department=department,
                    name=name,
                    defaults={
                        "unit": unit,
                        "target": target,
                        "higher_is_better": higher,
                        "auto_source": source,
                        "description": f"{description} Suggested target: please review.",
                    },
                )
                created += made
        self.stdout.write(self.style.SUCCESS(f"{created} suggested indicator(s) created."))
