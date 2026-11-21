"""Print / Save as PDF views (ministry decision 7). Each renders a standalone template extending print/base.html."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from . import indicators as target_svc
from .access import BRANCH, get_access, portal_view
from .dashboards import read_filters
from .models import Department, Indicator
from .printing import print_context

# Dashboards whose printout contains personal, pastoral or financial information.
SENSITIVE_DASHBOARDS = {"finance", "membership", "discipleship"}
MAX_PRINT_ROWS = 2000


def _dept_name(code: str) -> str:
    dept = Department.objects.filter(code=code).first()
    return dept.name if dept else code


@never_cache
@portal_view(level=BRANCH)
def dashboard_print(request: HttpRequest, department: str) -> HttpResponse:
    from .views import build_dashboard

    access = get_access(request)
    if department in SENSITIVE_DASHBOARDS and not access.is_head(department):
        raise PermissionDenied  # printouts of personal/financial dashboards: department head or Founder
    filters = read_filters(request, access, department)
    board = build_dashboard(request, department, filters)
    context = {
        "department": department,
        "board": board,
        "filters": filters,
        **print_context(
            request,
            title=f"{board.title}: dashboard report",
            department=_dept_name(department),
            branch=filters.branch_name,
            start=filters.start,
            end=filters.end,
            period_label=f"{filters.period_label}: {filters.start:%d %b %Y} to {filters.end:%d %b %Y}",
            fy=filters.fy,
            sensitive=department in SENSITIVE_DASHBOARDS,
            back_url=reverse("portal:dashboard", args=[department]),
            audit={"dashboard": department},
        ),
    }
    return render(request, "print/dashboard.html", context)


@never_cache
@portal_view(executive=True)
def executive_print(request: HttpRequest) -> HttpResponse:
    from .executive import build_overview

    access = get_access(request)
    filters = read_filters(request, access)
    context = {
        "overview": build_overview(request, access, filters),
        "filters": filters,
        **print_context(
            request,
            title="Executive overview",
            branch=filters.branch_name,
            start=filters.start,
            end=filters.end,
            period_label=f"{filters.period_label}: {filters.start:%d %b %Y} to {filters.end:%d %b %Y}",
            fy=filters.fy,
            back_url=reverse("portal:executive"),
        ),
    }
    return render(request, "print/executive.html", context)


@never_cache
@portal_view()
def targets_print(request: HttpRequest) -> HttpResponse:
    from .target_views import visible

    access = get_access(request)
    year_raw = request.GET.get("year", "")
    year = int(year_raw) if year_raw.isdigit() else timezone.localdate().year
    qs = visible(access)
    if not target_svc.can_manage(access) and not access.member_departments():
        raise PermissionDenied
    category = request.GET.get("category", "")
    if category in Indicator.Category.values:
        qs = qs.filter(category=category)
    department = request.GET.get("department", "")
    if department:
        qs = qs.filter(department__code=department)
    board = target_svc.board(qs, year)
    context = {
        "board": board,
        **print_context(
            request,
            title="Performance targets: target vs actual",
            department=_dept_name(department) if department else "",
            period_label=f"Year to date up to {board['month_label']}",
            fy=year,
            back_url=reverse("portal:targets"),
        ),
    }
    return render(request, "print/targets.html", context)


@never_cache
@portal_view(level=BRANCH)
def report_print(request: HttpRequest, department: str, pk: int) -> HttpResponse:
    from .resources import get_resource

    access = get_access(request)
    resource = get_resource(department, "reports")
    if resource is None or not resource.can(access, "view"):
        raise PermissionDenied
    report = get_object_or_404(resource.get_queryset(access), pk=pk)
    context = {
        "obj": report,
        **print_context(
            request,
            title=f"{report.department.name}: {report.get_period_display().lower()} report",
            department=report.department.name,
            start=report.period_start,
            end=report.period_end,
            period_label=report.period_label,
            fy=report.financial_year,
            sensitive=department in SENSITIVE_DASHBOARDS,
            back_url=reverse("portal:resource_detail", args=[department, "reports", report.pk]),
            audit={"report_id": report.pk},
        ),
    }
    context["report"]["prepared_by"] = (
        report.prepared_by.get_full_name() if report.prepared_by_id else ""  # type: ignore[union-attr]
    )
    return render(request, "print/department_report.html", context)


@never_cache
@portal_view(url_department=False)
def resource_print(request: HttpRequest, department: str, slug: str) -> HttpResponse:
    """A printed list is as sensitive as an export: it needs the export permission."""
    from .resources import get_resource

    access = get_access(request)
    resource = get_resource(department, slug)
    if resource is None or not resource.can(access, "view") or not resource.can(access, "export"):
        raise PermissionDenied
    qs = resource.apply_filters(resource.get_queryset(access), request.GET, access)
    total = qs.count()
    columns = resource.list_columns()
    rows = [[resource.value(obj, name) for name, _ in columns] for obj in qs[:MAX_PRINT_ROWS]]
    restricted, branch_id = access.branch_scope(department)
    branch = ""
    if restricted and branch_id:
        from branches.models import Branch

        branch = str(Branch.objects.filter(pk=branch_id).first() or "")
    elif request.GET.get("branch", "").isdigit():
        from branches.models import Branch

        branch = str(Branch.objects.filter(pk=int(request.GET["branch"])).first() or "")
    context = {
        "resource": resource,
        "columns": columns,
        "rows": rows,
        "total": total,
        "truncated": total > MAX_PRINT_ROWS,
        **print_context(
            request,
            title=resource.label,
            department=_dept_name(department),
            branch=branch,
            sensitive=resource.sensitive,
            back_url=reverse("portal:resource_list", args=[department, slug]),
            audit={"list": slug, "rows": min(total, MAX_PRINT_ROWS)},
        ),
    }
    return render(request, "print/resource_list.html", context)
