"""Cross-department flags for the Executive Overview: things leadership should know about today.

Counts only (no names or records). Each flag links to the screen where it can be dealt with; the link is hidden
from viewers who cannot open that department (``portal.executive``).
"""

from __future__ import annotations

from datetime import timedelta

from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone

from .dashboards import Item


def _url(department: str, slug: str, query: str = "") -> str:
    return reverse("portal:resource_list", args=[department, slug]) + (f"?{query}" if query else "")


def collect() -> list[Item]:
    from development.models import MaintenanceRequest, Milestone
    from discipleship.models import FollowUp
    from finance.models import BudgetLine, LedgerEntry
    from logistics.models import PurchaseOrder
    from membership.models import Member

    today = timezone.localdate()
    flags: list[Item] = []

    # Finance: departments over budget this year
    year = today.year
    spend = dict(
        LedgerEntry.objects.filter(status="posted", kind="expense", date__year=year)
        .values_list("department__name")
        .annotate(t=Sum("amount"))
    )
    budget = dict(
        BudgetLine.objects.filter(year=year).values_list("department__name").annotate(t=Sum("amount"))
    )
    over = [name for name, total in spend.items() if name and budget.get(name) and total > budget[name]]
    if over:
        flags.append(
            Item(
                f"Over budget in {year}: {', '.join(sorted(over))}",
                "Finance",
                _url("finance", "budget"),
                "bad",
            )
        )

    late = sum(1 for o in PurchaseOrder.objects.filter(expected_delivery__lt=today) if o.is_late)
    if late:
        flags.append(
            Item(f"{late} purchase order(s) delivered late", "Logistics", _url("logistics", "orders"), "bad")
        )

    overdue_follow = FollowUp.objects.filter(status="new", due_date__lt=today).count()
    if overdue_follow:
        flags.append(
            Item(
                f"{overdue_follow} new convert(s) not contacted on time",
                "Discipleship",
                _url("discipleship", "follow-ups", "status=new"),
                "bad",
            )
        )

    milestones = Milestone.objects.filter(completed_on__isnull=True, due_date__lt=today).count()
    if milestones:
        flags.append(
            Item(
                f"{milestones} building project milestone(s) overdue",
                "Development",
                _url("development", "projects"),
                "bad",
            )
        )

    urgent = MaintenanceRequest.objects.filter(priority="urgent").exclude(status="done").count()
    if urgent:
        flags.append(
            Item(
                f"{urgent} urgent (safety) maintenance request(s) open",
                "Development",
                _url("development", "maintenance", "priority=urgent"),
                "bad",
            )
        )

    waiting = Member.objects.filter(
        status__in=Member.PENDING, created_at__lt=timezone.now() - timedelta(days=14)
    ).count()
    if waiting:
        flags.append(
            Item(
                f"{waiting} membership application(s) waiting over two weeks",
                "Membership",
                _url("membership", "members", "status=submitted"),
                "warn",
            )
        )
    return flags
