"""M&E screens, registered once per department: indicators, their values, and periodic reports."""

from __future__ import annotations

from typing import Any, ClassVar

from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.urls import reverse

from .access import DEPARTMENT_ORDER, FOUNDER, HEAD, MEMBER, Access
from .models import Department, DepartmentReport, Indicator, IndicatorValue
from .resources import Resource, register


class _DepartmentScoped(Resource):
    department_lookup = "department__code"
    nav_group = "Monitoring & evaluation"

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        return qs.filter(**{self.department_lookup: self.department})

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        super().before_save(request, access, obj, created)
        if hasattr(obj, "department_id") and not obj.department_id:
            obj.department = Department.objects.get(code=self.department)


class IndicatorResource(_DepartmentScoped):
    model = Indicator
    slug = "indicators"
    icon = "target"
    list_fields: ClassVar = ["name", "unit", "target", "period", "latest", "is_active"]
    filters: ClassVar = ["period", "is_active"]
    fields: ClassVar = [
        "name",
        "description",
        "unit",
        "target",
        "period",
        "higher_is_better",
        "auto_source",
        "is_active",
    ]
    children: ClassVar = [("values", "indicator-values", "Recorded values")]
    perms: ClassVar = {"add": HEAD, "change": HEAD, "delete": HEAD}

    def latest(self, obj: Indicator) -> Any:
        value = obj.latest_value()
        if value is None:
            return "—"
        return f"{value.value:,.2f} ({value.period_start:%b %Y})"

    latest.short_description = "Latest value"  # type: ignore[attr-defined]


class IndicatorValueResource(_DepartmentScoped):
    model = IndicatorValue
    slug = "indicator-values"
    nav = False
    department_lookup = "indicator__department__code"
    parent_field = "indicator"
    list_fields: ClassVar = ["indicator", "period_start", "value", "progress_pct", "note"]
    fields: ClassVar = ["indicator", "period_start", "value", "note"]
    perms: ClassVar = {"add": MEMBER, "change": MEMBER, "delete": HEAD}

    def progress_pct(self, obj: IndicatorValue) -> str:
        return "—" if obj.progress is None else f"{obj.progress}%"

    progress_pct.short_description = "Progress to target"  # type: ignore[attr-defined]

    def limit_choices(self, access: Access, field_name: str, related: type[Model]) -> QuerySet:
        if field_name == "indicator":
            return Indicator.objects.filter(department__code=self.department)
        return super().limit_choices(access, field_name, related)


class ReportResource(_DepartmentScoped):
    model = DepartmentReport
    slug = "reports"
    icon = "report"
    label = "Reports"
    list_fields: ClassVar = ["period_label", "status", "submitted_at", "reviewed_at"]
    filters: ClassVar = ["status", "period"]
    fields: ClassVar = ["highlights", "challenges", "plans_next_period", "support_needed"]
    detail_template = "portal/report_detail.html"
    perms: ClassVar = {"view": MEMBER, "add": FOUNDER + 1, "change": HEAD, "delete": FOUNDER, "export": HEAD}

    def period_label(self, obj: DepartmentReport) -> str:
        return obj.period_label

    period_label.short_description = "Period"  # type: ignore[attr-defined]

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        if action == "change":
            return obj.is_editable  # type: ignore[attr-defined]
        return True

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        report: DepartmentReport = obj  # type: ignore[assignment]
        out = []
        if report.is_editable and access.is_head(self.department):
            out.append(
                {
                    "label": "Submit to the Founder",
                    "url": reverse("portal:report_submit", args=[self.department, report.pk]),
                    "style": "primary",
                    "confirm": "Submit this report? You cannot edit it afterwards unless it is returned.",
                }
            )
        return out


for _code in DEPARTMENT_ORDER:
    for _base in (IndicatorResource, IndicatorValueResource, ReportResource):
        register(type(f"{_base.__name__}_{_code}", (_base,), {"department": _code, "__module__": __name__}))
