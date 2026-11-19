"""Executive Overview: one page for the Founder and designated leadership.

Department summaries are AGGREGATE figures only (counts and totals, never names or records). Every
drill-down link is shown only when the viewer may open that department, so the page never becomes a way
around department scoping.
"""

from __future__ import annotations

from typing import Any

from django.http import HttpRequest
from django.urls import reverse

from .access import DEPARTMENT_ORDER, Access
from .dashboards import EXECUTIVE_SUMMARIES, HANDOFFS, PENDING_APPROVALS, Filters, Item
from .models import Department, Indicator
from .reports import report_status


def build_overview(request: HttpRequest, access: Access, filters: Filters) -> dict[str, Any]:
    departments = {d.code: d for d in Department.objects.all()}
    cards = []
    for code in DEPARTMENT_ORDER:
        summary = EXECUTIVE_SUMMARIES.get(code)
        can_open = access.can_enter(code)
        cards.append(
            {
                "code": code,
                "department": departments.get(code),
                "kpis": summary(filters) if summary else [],
                "url": reverse("portal:dashboard", args=[code]) if can_open else "",
            }
        )

    indicators = []
    for indicator in Indicator.objects.filter(is_active=True).select_related("department"):
        latest = indicator.latest_value()
        indicators.append(
            {
                "indicator": indicator,
                "value": latest.value if latest else None,
                "period": latest.period_start if latest else None,
                "progress": latest.progress if latest else None,
            }
        )

    pending: list[Item] = []
    for code in DEPARTMENT_ORDER:
        builder = PENDING_APPROVALS.get(code)
        if builder is None:
            continue
        for item in builder():
            if not access.can_enter(code):
                item.url = ""
            pending.append(item)

    handoffs: list[Item] = []
    for builder in HANDOFFS:
        for item in builder():
            if item.url and not _url_allowed(item.url, access):
                item.url = ""
            handoffs.append(item)

    from .flags import collect

    flags = collect()
    for item in flags:
        if item.url and not _url_allowed(item.url, access):
            item.url = ""

    reports = report_status()
    for row in reports:
        if row["report"] is not None and access.can_enter(row["department"].code):
            row["url"] = reverse(
                "portal:resource_detail", args=[row["department"].code, "reports", row["report"].pk]
            )
    return {
        "cards": cards,
        "indicators": indicators,
        "pending": pending,
        "handoffs": handoffs,
        "flags": flags,
        "reports": reports,
        "overdue": [r for r in reports if r["overdue"]],
        "awaiting_review": [r for r in reports if r["awaiting_review"]],
    }


def _url_allowed(url: str, access: Access) -> bool:
    for code in DEPARTMENT_ORDER:
        if f"/{code}/" in url:
            return access.can_enter(code)
    return access.is_super_admin
