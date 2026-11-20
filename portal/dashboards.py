"""Dashboard building blocks. Each department module registers a builder that returns a ``Dashboard``.

Builders receive the ``Access`` and the validated ``Filters`` and must compute every figure from querysets
that are already scoped for that user (``Resource.get_queryset`` or ``access.restrict_branch``).
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest
from django.utils import timezone

from .access import Access
from .charts import Chart
from .resources import parse_date


@dataclass
class KPI:
    label: str
    value: Any
    hint: str = ""
    url: str = ""
    code: str = ""  # stable key for reports and M&E auto-fill
    status: str = ""  # "", "good", "warn", "bad" (always shown with an icon + word, never colour alone)


@dataclass
class Item:
    text: str
    meta: str = ""
    url: str = ""
    status: str = ""


@dataclass
class Action:
    label: str
    url: str
    primary: bool = False


@dataclass
class Dashboard:
    title: str
    purpose: str = ""
    kpis: list[KPI] = field(default_factory=list)
    charts: list[Chart] = field(default_factory=list)
    attention: list[Item] = field(default_factory=list)
    activity: list[Item] = field(default_factory=list)
    actions: list[Action] = field(default_factory=list)
    sections: list[dict[str, Any]] = field(default_factory=list)  # extra tables: {"title", "columns", "rows"}
    timeline: dict[str, Any] | None = None  # Gantt-style geometry from portal.charts.timeline
    timeline_title: str = ""

    def figures(self) -> list[dict[str, Any]]:
        return [{"code": k.code, "label": k.label, "value": str(k.value)} for k in self.kpis]


@dataclass
class Filters:
    start: dt.date
    end: dt.date
    branch_id: int | None = None
    branch_name: str = ""
    fy: int | None = None  # financial year (= calendar year, ministry decision 2)
    period: str = ""  # "" whole year, "q1".."q4", "m1".."m12"; "custom" for an explicit date range

    def __post_init__(self) -> None:
        if self.fy is None:
            self.fy = self.end.year

    @property
    def start_dt(self) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(self.start, dt.time.min))

    @property
    def end_dt(self) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(self.end, dt.time.max))

    def branch_filter(self, lookup: str) -> dict[str, Any]:
        return {lookup: self.branch_id} if self.branch_id else {}

    @property
    def period_label(self) -> str:
        if self.period.startswith("q"):
            return f"Q{self.period[1:]} {self.fy}"
        if self.period.startswith("m"):
            return f"{dt.date(self.fy or self.end.year, int(self.period[1:]), 1):%B} {self.fy}"
        if self.period == "custom":
            return f"{self.start:%d %b %Y} to {self.end:%d %b %Y}"
        return f"Financial year {self.fy}"

    def as_query(self) -> dict[str, str]:
        if self.period == "custom":
            query = {"from": self.start.isoformat(), "to": self.end.isoformat()}
        else:
            query = {"fy": str(self.fy), "period": self.period}
        if self.branch_id:
            query["branch"] = str(self.branch_id)
        return query


PERIOD_CHOICES = (
    [("", "Whole year")]
    + [(f"q{q}", f"Quarter {q}") for q in range(1, 5)]
    + [(f"m{m}", dt.date(2000, m, 1).strftime("%B")) for m in range(1, 13)]
)


def period_range(fy: int, period: str) -> tuple[dt.date, dt.date]:
    """Quarters and months derive from the calendar year (FY = 1 January to 31 December)."""
    if period.startswith("q") and period[1:] in ("1", "2", "3", "4"):
        first = (int(period[1:]) - 1) * 3 + 1
        start = dt.date(fy, first, 1)
        last_month = first + 2
    elif period.startswith("m") and period[1:].isdigit() and 1 <= int(period[1:]) <= 12:
        start = dt.date(fy, int(period[1:]), 1)
        last_month = int(period[1:])
    else:
        return dt.date(fy, 1, 1), dt.date(fy, 12, 31)
    nxt = dt.date(fy + (last_month == 12), last_month % 12 + 1, 1)
    return start, nxt - dt.timedelta(days=1)


def financial_years() -> list[int]:
    from finance.models import FinancialYear

    today = timezone.localdate()
    years = set(FinancialYear.objects.values_list("year", flat=True)) | {today.year, today.year - 1}
    return sorted(years, reverse=True)


def read_filters(request: HttpRequest, access: Access, department: str | None = None) -> Filters:
    today = timezone.localdate()
    custom_start, custom_end = parse_date(request.GET.get("from")), parse_date(request.GET.get("to"))
    if custom_start or custom_end:
        start, end, period = custom_start or dt.date(today.year, 1, 1), custom_end or today, "custom"
        if start > end:
            start, end = end, start
        if (end - start).days > 366 * 5:
            start = end - dt.timedelta(days=366 * 5)
        fy = end.year
    else:
        raw_fy = request.GET.get("fy", "")
        fy = int(raw_fy) if raw_fy.isdigit() and 2000 <= int(raw_fy) <= 2100 else today.year
        period = request.GET.get("period", "")
        if period not in {code for code, _ in PERIOD_CHOICES}:
            period = ""
        start, end = period_range(fy, period)
    branch_id: int | None = None
    branch_name = ""
    raw = request.GET.get("branch", "")
    allowed = access.allowed_branches(department)
    restricted, scope_branch = access.branch_scope(department)
    if restricted:
        branch_id = scope_branch
    elif raw.isdigit() and allowed.filter(pk=int(raw)).exists():
        branch_id = int(raw)
    if branch_id:
        branch_name = str(allowed.filter(pk=branch_id).first() or "")
    return Filters(start=start, end=end, branch_id=branch_id, branch_name=branch_name, fy=fy, period=period)


Builder = Callable[[HttpRequest, Access, Filters], Dashboard]
DASHBOARDS: dict[str, Builder] = {}
EXECUTIVE_SUMMARIES: dict[str, Callable[[Access, Filters], list[KPI]]] = {}
PENDING_APPROVALS: dict[str, Callable[[Access], list[Item]]] = {}
HANDOFFS: list[Callable[[Access], list[Item]]] = []


def dashboard(code: str) -> Callable[[Builder], Builder]:
    def decorator(fn: Builder) -> Builder:
        DASHBOARDS[code] = fn
        return fn

    return decorator


def executive_summary(code: str):  # type: ignore[no-untyped-def]
    def decorator(fn):  # type: ignore[no-untyped-def]
        EXECUTIVE_SUMMARIES[code] = fn
        return fn

    return decorator


def pending_approvals(code: str):  # type: ignore[no-untyped-def]
    def decorator(fn):  # type: ignore[no-untyped-def]
        PENDING_APPROVALS[code] = fn
        return fn

    return decorator


def handoffs(fn):  # type: ignore[no-untyped-def]
    HANDOFFS.append(fn)
    return fn
