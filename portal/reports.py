"""M&E services: indicator progress, report generation, submission and Founder review."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .dashboards import Filters
from .models import Department, DepartmentReport, Indicator, IndicatorValue, Period, period_end, period_start


def indicator_progress(department: str) -> list[dict[str, Any]]:
    rows = []
    for indicator in Indicator.objects.filter(department__code=department, is_active=True).select_related(
        "department"
    ):
        latest = indicator.latest_value()
        rows.append(
            {
                "indicator": indicator,
                "value": latest.value if latest else None,
                "period": latest.period_start if latest else None,
                "progress": latest.progress if latest else None,
            }
        )
    return rows


def recent_reports(department: str, limit: int = 4) -> list[DepartmentReport]:
    return list(DepartmentReport.objects.filter(department__code=department)[:limit])


def previous_month(today: dt.date) -> dt.date:
    return (today.replace(day=1) - dt.timedelta(days=1)).replace(day=1)


def resolve_period(period: str, month: str | None) -> tuple[str, dt.date]:
    if period not in Period.values:
        period = Period.MONTHLY
    start = None
    if month:
        try:
            start = dt.date.fromisoformat(f"{month[:7]}-01")
        except ValueError:
            start = None
    if start is None:
        start = previous_month(timezone.localdate())
    return period, period_start(start, period)


def _decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value).replace(",", "").split(" ")[0])
    except (InvalidOperation, ValueError):
        return None


@transaction.atomic
def generate(request: HttpRequest, department: str, period: str, month: str | None) -> DepartmentReport:
    from .views import build_dashboard

    dept = Department.objects.get(code=department)
    period, start = resolve_period(period, month)
    end = period_end(start, period)
    board = build_dashboard(request, department, Filters(start=start, end=end))
    figures = board.figures()
    by_code = {f["code"]: f["value"] for f in figures if f["code"]}

    indicator_rows = []
    for indicator in Indicator.objects.filter(department=dept, is_active=True, period=period):
        value_obj = IndicatorValue.objects.filter(indicator=indicator, period_start=start).first()
        if indicator.auto_source and indicator.auto_source in by_code:
            auto = _decimal(by_code[indicator.auto_source])
            if auto is not None:
                value_obj, _ = IndicatorValue.objects.update_or_create(
                    indicator=indicator,
                    period_start=start,
                    defaults={
                        "value": auto,
                        "note": "Filled automatically from the dashboard.",
                        "entered_by": request.user,
                    },
                )
        indicator_rows.append(
            {
                "name": indicator.name,
                "unit": indicator.unit,
                "target": str(indicator.target),
                "value": str(value_obj.value) if value_obj else "",
                "progress": value_obj.progress if value_obj else None,
            }
        )

    report = DepartmentReport.objects.filter(department=dept, period=period, period_start=start).first()
    if report is not None and not report.is_editable:
        raise ValidationError("This report was already submitted; ask the Founder to return it for changes.")
    created = report is None
    if report is None:
        report = DepartmentReport(
            department=dept, period=period, period_start=start, prepared_by=request.user
        )
    report.figures = figures
    report.indicators = indicator_rows
    report.save()
    log_event(AuditLog.Action.ADD if created else AuditLog.Action.CHANGE, request=request, obj=report)
    return report


def submit(request: HttpRequest, report: DepartmentReport) -> None:
    if not report.is_editable:
        raise PermissionDenied
    report.status = DepartmentReport.Status.SUBMITTED
    report.submitted_at = timezone.now()
    report.prepared_by = report.prepared_by or request.user
    report.save()
    log_event(AuditLog.Action.SUBMIT, request=request, obj=report)


def review(request: HttpRequest, report: DepartmentReport, *, accept: bool, comment: str) -> None:
    if report.status != DepartmentReport.Status.SUBMITTED:
        raise PermissionDenied
    report.status = DepartmentReport.Status.REVIEWED if accept else DepartmentReport.Status.RETURNED
    report.reviewed_by = request.user
    report.reviewed_at = timezone.now()
    report.review_comment = comment[:2000]
    report.save()
    log_event(AuditLog.Action.APPROVE if accept else AuditLog.Action.REJECT, request=request, obj=report)


def report_status(today: dt.date | None = None) -> list[dict[str, Any]]:
    """Last completed month's report state for every department (for the Executive Overview)."""
    today = today or timezone.localdate()
    start = previous_month(today)
    due_day = getattr(settings, "REPORT_DUE_DAY", 10)
    due = today.replace(day=min(due_day, 28)) if today.month != start.month else today
    rows = []
    existing = {
        r.department_id: r
        for r in DepartmentReport.objects.filter(period=Period.MONTHLY, period_start=start).select_related(
            "department"
        )
    }
    for dept in Department.objects.all():
        report = existing.get(dept.pk)
        status = report.get_status_display() if report else "Not started"
        done = report is not None and report.status in (
            DepartmentReport.Status.SUBMITTED,
            DepartmentReport.Status.REVIEWED,
        )
        rows.append(
            {
                "department": dept,
                "report": report,
                "period": start,
                "status": status,
                "overdue": not done and today > due,
                "awaiting_review": report is not None and report.status == DepartmentReport.Status.SUBMITTED,
            }
        )
    return rows
