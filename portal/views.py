"""Portal views: landing, department dashboards, executive overview, and the generic resource screens."""

from __future__ import annotations

import csv
import os
from collections.abc import Iterable
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import ProtectedError
from django.http import FileResponse, Http404, HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from audit.models import AuditLog
from audit.services import log_event
from core.admin_mixins import Echo, csv_safe

from . import reports
from .access import HEAD, MEMBER, get_access, portal_view
from .dashboards import DASHBOARDS, KPI, PERIOD_CHOICES, Dashboard, financial_years, read_filters
from .models import Department
from .resources import Resource, format_value, get_resource, resources_for


def is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


# ------------------------------------------------------------------------------------------- landing
@never_cache
@portal_view()
def home(request: HttpRequest) -> HttpResponse:
    return redirect(get_access(request).home_url())


@never_cache
@portal_view()
def no_access(request: HttpRequest) -> HttpResponse:
    return render(request, "portal/no_access.html", status=403)


# ------------------------------------------------------------------------------------------- dashboards
def build_dashboard(request: HttpRequest, department: str, filters: Any) -> Dashboard:
    access = get_access(request)
    builder = DASHBOARDS.get(department)
    dept = Department.objects.filter(code=department).first()
    board = builder(request, access, filters) if builder else Dashboard(title=str(dept or department))
    if dept and not board.purpose:
        board.purpose = dept.purpose
    return board


@never_cache
@portal_view(level=1)
def dashboard(request: HttpRequest, department: str) -> HttpResponse:
    access = get_access(request)
    filters = read_filters(request, access, department)
    board = build_dashboard(request, department, filters)
    context = {
        "department": department,
        "board": board,
        "filters": filters,
        "branches": access.allowed_branches(department),
        "branch_fixed": access.branch_restricted_in(department),
        "fy_choices": financial_years(),
        "period_choices": PERIOD_CHOICES,
        "can_export": access.is_head(department),
        "indicators": reports.indicator_progress(department),
        "reports": reports.recent_reports(department),
    }
    if is_htmx(request):
        return render(request, "portal/_dashboard_body.html", context)
    return render(request, "portal/dashboard.html", context)


@never_cache
@portal_view(level=HEAD)
def dashboard_export(request: HttpRequest, department: str, fmt: str) -> HttpResponse:
    access = get_access(request)
    filters = read_filters(request, access, department)
    board = build_dashboard(request, department, filters)
    log_event(
        AuditLog.Action.EXPORT,
        request=request,
        model=Department,
        extra={"dashboard": department, "format": fmt, **filters.as_query()},
    )
    if fmt == "csv":
        response = HttpResponse(content_type="text/csv; charset=utf-8")
        writer = csv.writer(response)
        writer.writerow(["Dashboard", board.title])
        writer.writerow(["Period", filters.start.isoformat(), filters.end.isoformat()])
        writer.writerow(["Branch", filters.branch_name or "All branches"])
        writer.writerow([])
        writer.writerow(["Figure", "Value", "Code (for automatic target values)"])
        for kpi in board.kpis:
            writer.writerow([csv_safe(kpi.label), csv_safe(kpi.value), kpi.code])
        for chart in board.charts:
            writer.writerow([])
            writer.writerow([csv_safe(chart.title), ""])
            for label, value in chart.rows:
                writer.writerow([csv_safe(label), csv_safe(value)])
        stamp = timezone.now().strftime("%Y%m%d-%H%M")
        response["Content-Disposition"] = f'attachment; filename="{department}-dashboard-{stamp}.csv"'
        response["Cache-Control"] = "no-store"
        return response
    if fmt == "print":
        return render(
            request,
            "portal/dashboard_print.html",
            {"department": department, "board": board, "filters": filters, "now": timezone.now()},
        )
    raise Http404


# ------------------------------------------------------------------------------------------- executive
@never_cache
@portal_view(executive=True)
def executive(request: HttpRequest) -> HttpResponse:
    from .executive import build_overview

    access = get_access(request)
    filters = read_filters(request, access)
    context = {
        "overview": build_overview(request, access, filters),
        "filters": filters,
        "fy_choices": financial_years(),
        "period_choices": PERIOD_CHOICES,
    }
    context["branches"] = access.allowed_branches()
    if is_htmx(request):
        return render(request, "portal/_executive_body.html", context)
    return render(request, "portal/executive.html", context)


# ------------------------------------------------------------------------------------------- resources
def _resource_or_404(request: HttpRequest, department: str, slug: str, action: str) -> Resource:
    resource = get_resource(department, slug)
    if resource is None:
        raise Http404
    if not resource.can(get_access(request), action):
        raise PermissionDenied
    return resource


def _object_or_404(request: HttpRequest, resource: Resource, pk: int, action: str) -> Any:
    access = get_access(request)
    obj = get_object_or_404(resource.get_queryset(access), pk=pk)  # out of scope -> 404 (no IDOR)
    if not resource.can(access, action, obj):
        raise PermissionDenied
    return obj


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
def resource_list(request: HttpRequest, department: str, slug: str) -> HttpResponse:
    access = get_access(request)
    resource = _resource_or_404(request, department, slug, "view")
    qs = resource.apply_filters(resource.get_queryset(access), request.GET, access)
    page = Paginator(qs, resource.page_size).get_page(request.GET.get("page"))
    columns = resource.list_columns()
    rows = [(obj, [resource.value(obj, name) for name, _ in columns]) for obj in page.object_list]
    if resource.sensitive:
        log_event(
            AuditLog.Action.VIEW,
            request=request,
            model=resource.model,
            extra={"list": True, "shown": len(rows), "page": page.number},
        )
    query = request.GET.copy()
    query.pop("page", None)
    context = {
        "department": department,
        "resource": resource,
        "columns": columns,
        "rows": rows,
        "page": page,
        "filter_specs": resource.filter_specs(access),
        "params": request.GET,
        "query": query.urlencode(),
        "can_add": resource.can(access, "add"),
        "can_export": resource.can(access, "export"),
    }
    if is_htmx(request):
        return render(request, "portal/resource/_table.html", context)
    return render(request, "portal/resource/list.html", context)


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
def resource_detail(request: HttpRequest, department: str, slug: str, pk: int) -> HttpResponse:
    access = get_access(request)
    resource = _resource_or_404(request, department, slug, "view")
    obj = _object_or_404(request, resource, pk, "view")
    if resource.sensitive:
        log_event(AuditLog.Action.VIEW, request=request, obj=obj)
    children = []
    for accessor, child_slug, title in resource.children:
        child = get_resource(department, child_slug)
        if child is None or not child.can(access, "view"):
            continue
        related = getattr(obj, accessor)
        child_qs = child.get_queryset(access).filter(pk__in=related.values("pk"))[:50]
        columns = child.list_columns()
        children.append(
            {
                "title": title,
                "resource": child,
                "columns": columns,
                "rows": [(c, [child.value(c, n) for n, _ in columns]) for c in child_qs],
                "add_url": child.url("create", parent=obj.pk) if child.can(access, "add") else "",
            }
        )
    context = {
        "department": department,
        "resource": resource,
        "obj": obj,
        "rows": resource.detail_rows(obj),
        "children": children,
        "actions": resource.actions(request, access, obj),
        "can_change": resource.can(access, "change", obj) and resource.fields is not None,
        "can_delete": resource.can(access, "delete", obj),
        **resource.extra_context(request, access, obj),
    }
    return render(request, getattr(resource, "detail_template", "portal/resource/detail.html"), context)


def _changed_names(form: Any) -> list[str]:
    return sorted(form.changed_data)


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
@require_http_methods(["GET", "POST"])
def resource_form(request: HttpRequest, department: str, slug: str, pk: int | None = None) -> HttpResponse:
    access = get_access(request)
    action = "add" if pk is None else "change"
    resource = _resource_or_404(request, department, slug, action)
    if resource.fields is None and resource.form_class is None:
        raise Http404
    obj = None if pk is None else _object_or_404(request, resource, pk, "change")
    form_class = resource.get_form_class(access, obj)
    kwargs: dict[str, Any] = {"instance": obj}
    if "access" in form_class.__init__.__code__.co_varnames:
        kwargs["access"] = access
    if request.method == "POST":
        form = form_class(request.POST, request.FILES, **kwargs)
    else:
        form = form_class(initial=resource.initial(request, access) if obj is None else None, **kwargs)
    resource.prepare_form(form, access)
    if request.method == "POST" and form.is_valid():
        created = obj is None
        with transaction.atomic():
            instance = form.save(commit=False)
            resource.before_save(request, access, instance, created)
            instance.save()
            form.save_m2m()
            # Re-check scope after saving: a user can never create or move a record out of their own reach.
            if not resource.get_queryset(access).filter(pk=instance.pk).exists():
                transaction.set_rollback(True)
                raise PermissionDenied
            resource.after_save(request, access, instance, created)
            log_event(
                AuditLog.Action.ADD if created else AuditLog.Action.CHANGE,
                request=request,
                obj=instance,
                extra={"fields": _changed_names(form)},
            )
        messages.success(request, f"{resource.label_singular} saved.")
        return redirect(resource.url("detail", instance))
    context = {"department": department, "resource": resource, "form": form, "obj": obj}
    return render(request, "portal/resource/form.html", context)


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
@require_http_methods(["GET", "POST"])
def resource_delete(request: HttpRequest, department: str, slug: str, pk: int) -> HttpResponse:
    resource = _resource_or_404(request, department, slug, "delete")
    obj = _object_or_404(request, resource, pk, "delete")
    if request.method == "POST":
        log_event(AuditLog.Action.DELETE, request=request, obj=obj)
        try:
            obj.delete()
        except (ProtectedError, PermissionError) as exc:
            messages.error(request, f"This record cannot be deleted: {exc.args[0] if exc.args else ''}")
            return redirect(resource.url("detail", obj))
        messages.success(request, f"{resource.label_singular} deleted.")
        return redirect(resource.url("list"))
    return render(
        request, "portal/resource/delete.html", {"department": department, "resource": resource, "obj": obj}
    )


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
def resource_export(request: HttpRequest, department: str, slug: str) -> StreamingHttpResponse:
    access = get_access(request)
    resource = _resource_or_404(request, department, slug, "export")
    qs = resource.apply_filters(resource.get_queryset(access), request.GET, access)
    names = resource.export_fields or [n for n in (resource.fields or resource.list_fields) if n != "__str__"]
    labels = [resource.column_label(n) for n in names]
    count = qs.count()
    log_event(
        AuditLog.Action.EXPORT,
        request=request,
        model=resource.model,
        extra={"count": count, "fields": names, "department": department},
    )
    writer = csv.writer(Echo())

    def stream() -> Iterable[str]:
        yield writer.writerow(["ID", *labels])
        for obj in qs.iterator():
            yield writer.writerow([obj.pk, *[csv_safe(resource.value(obj, n)) for n in names]])

    response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
    stamp = timezone.now().strftime("%Y%m%d-%H%M")
    response["Content-Disposition"] = f'attachment; filename="{department}-{slug}-{stamp}.csv"'
    response["Cache-Control"] = "no-store"
    return response


@never_cache
@portal_view(url_department=False)  # Resource.can() decides (department, branch, requester)
def resource_file(request: HttpRequest, department: str, slug: str, pk: int, field: str) -> FileResponse:
    resource = _resource_or_404(request, department, slug, "view")
    obj = _object_or_404(request, resource, pk, "view")
    allowed = {name for _, _, name in resource.detail_rows(obj)}
    if field not in allowed:
        raise Http404
    file = getattr(obj, field, None)
    if not file:
        raise Http404
    log_event(AuditLog.Action.VIEW, request=request, obj=obj, extra={"file": field})
    ext = os.path.splitext(file.name)[1].lower()
    response = FileResponse(file.open("rb"), as_attachment=True, filename=f"{slug}-{obj.pk}-{field}{ext}")
    response["Cache-Control"] = "no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


# ------------------------------------------------------------------------------------------- workflow helper
def post_action(
    request: HttpRequest, department: str, slug: str, pk: int, action: str = "change"
) -> tuple[Resource, Any]:
    """Shared guard for workflow POST views: resource access + object in scope."""
    resource = _resource_or_404(request, department, slug, action)
    return resource, _object_or_404(request, resource, pk, action)


# ------------------------------------------------------------------------------------------- reports
@never_cache
@portal_view(level=HEAD)
@require_POST
def report_generate(request: HttpRequest, department: str) -> HttpResponse:
    report = reports.generate(
        request, department, request.POST.get("period", "monthly"), request.POST.get("month")
    )
    messages.success(
        request, f"Report for {report.period_label} is ready. Add the narrative, then submit it."
    )
    return redirect(get_resource(department, "reports").url("detail", report))


@never_cache
@portal_view(level=HEAD)
@require_POST
def report_submit(request: HttpRequest, department: str, pk: int) -> HttpResponse:
    resource, report = post_action(request, department, "reports", pk, "change")
    reports.submit(request, report)
    messages.success(request, "Report submitted to the Founder.")
    return redirect(resource.url("detail", report))


@never_cache
@portal_view(super_admin=True)
@require_POST
def report_review(request: HttpRequest, department: str, pk: int) -> HttpResponse:
    resource, report = post_action(request, department, "reports", pk, "view")
    reports.review(
        request,
        report,
        accept=request.POST.get("decision") == "accept",
        comment=request.POST.get("comment", ""),
    )
    messages.success(request, "Review recorded.")
    return redirect(resource.url("detail", report))


@never_cache
@portal_view(level=MEMBER)
def department_resources(request: HttpRequest, department: str) -> HttpResponse:
    """Index of every screen in a department (useful on phones)."""
    access = get_access(request)
    items = [r for r in resources_for(department) if r.can(access, "view")]
    return render(request, "portal/department_index.html", {"department": department, "items": items})


__all__ = ["KPI", "format_value"]
