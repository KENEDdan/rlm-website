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

    @property
    def start_dt(self) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(self.start, dt.time.min))

    @property
    def end_dt(self) -> dt.datetime:
        return timezone.make_aware(dt.datetime.combine(self.end, dt.time.max))

    def branch_filter(self, lookup: str) -> dict[str, Any]:
        return {lookup: self.branch_id} if self.branch_id else {}

    def as_query(self) -> dict[str, str]:
        query = {"from": self.start.isoformat(), "to": self.end.isoformat()}
        if self.branch_id:
            query["branch"] = str(self.branch_id)
        return query


def default_start(today: dt.date) -> dt.date:
    month = today.month - 11
    year = today.year
    while month <= 0:
        month += 12
        year -= 1
    return dt.date(year, month, 1)


def read_filters(request: HttpRequest, access: Access) -> Filters:
    today = timezone.localdate()
    start = parse_date(request.GET.get("from")) or default_start(today)
    end = parse_date(request.GET.get("to")) or today
    if start > end:
        start, end = end, start
    if (end - start).days > 366 * 5:
        start = end - dt.timedelta(days=366 * 5)
    branch_id: int | None = None
    branch_name = ""
    raw = request.GET.get("branch", "")
    allowed = access.allowed_branches()
    if access.branch_restricted:
        branch_id = access.branch_id
    elif raw.isdigit() and allowed.filter(pk=int(raw)).exists():
        branch_id = int(raw)
    if branch_id:
        branch_name = str(allowed.filter(pk=branch_id).first() or "")
    return Filters(start=start, end=end, branch_id=branch_id, branch_name=branch_name)


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
