"""Performance targets screens (ministry decision 4).

* Leadership (Founder / Super Admin, Executive Leadership): see every target, create, adjust (with a reason),
  import a CSV.
* Departments: see their own targets (within their branch scope) and record monthly actuals.
"""

from __future__ import annotations

import base64
import datetime as dt
from decimal import Decimal, InvalidOperation
from typing import Any

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q, QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from audit.models import AuditLog
from audit.services import log_event

from . import indicators as svc
from .access import BRANCH, MEMBER, Access, get_access, portal_view
from .models import Department, Indicator

SESSION_IMPORT = "targets_import_csv"


def visible(access: Access) -> QuerySet:
    """Leadership: all targets. Departments: their own, limited to their branch where their role is scoped."""
    qs = Indicator.objects.select_related("department", "branch")
    if svc.can_manage(access):
        return qs
    cond = Q(pk__in=[])
    for code in access.member_departments():
        restricted, branch_id = access.branch_scope(code)
        if restricted:
            cond |= Q(department__code=code, branch_id=branch_id)
        else:
            cond |= Q(department__code=code)
    if access.is_branch_coordinator and access.user.branch_id:
        for code in ("membership", "missions", "discipleship"):
            if access.level(code) == BRANCH:
                cond |= Q(department__code=code, branch_id=access.user.branch_id)
    return qs.filter(cond)


def can_record(access: Access, indicator: Indicator) -> bool:
    if access.is_super_admin:
        return True
    if access.level(indicator.department.code) < (BRANCH if access.is_branch_coordinator else MEMBER):
        return False
    return visible(access).filter(pk=indicator.pk).exists()


def _years() -> list[int]:
    today = timezone.localdate()
    years = set(Indicator.objects.values_list("year", flat=True)) | {today.year, today.year + 1}
    return sorted(years, reverse=True)


# ------------------------------------------------------------------------------------------------ list
@never_cache
@portal_view()
def target_list(request: HttpRequest) -> HttpResponse:
    access = get_access(request)
    qs = visible(access)
    if not svc.can_manage(access) and not qs.exists() and not access.member_departments():
        raise PermissionDenied
    year_raw = request.GET.get("year", "")
    year = int(year_raw) if year_raw.isdigit() else timezone.localdate().year
    category = request.GET.get("category", "")
    if category in Indicator.Category.values:
        qs = qs.filter(category=category)
    department = request.GET.get("department", "")
    if department:
        qs = qs.filter(department__code=department)
    board = svc.board(qs, year)
    return render(
        request,
        "portal/targets/list.html",
        {
            "board": board,
            "years": _years(),
            "year": year,
            "category": category,
            "department": department,
            "categories": Indicator.Category.choices,
            "departments": Department.objects.all(),
            "can_manage": svc.can_manage(access),
            "rag_rule": f"Green {svc.GREEN}%+ of target, Amber {svc.AMBER}-{svc.GREEN - 1}%, Red below {svc.AMBER}%",
        },
    )


# ------------------------------------------------------------------------------------------------ create
class TargetForm(forms.ModelForm):
    class Meta:
        model = Indicator
        fields = [
            "category",
            "name",
            "department",
            "branch",
            "year",
            "unit",
            "annual_target",
            "higher_is_better",
            "description",
            "auto_source",
        ]

    def clean_annual_target(self) -> Decimal:
        value = self.cleaned_data["annual_target"]
        if value < 0:
            raise ValidationError("A target cannot be negative.")
        return value


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def target_create(request: HttpRequest) -> HttpResponse:
    access = get_access(request)
    if not svc.can_manage(access):
        raise PermissionDenied
    form = TargetForm(request.POST or None, initial={"year": timezone.localdate().year})
    if request.method == "POST" and form.is_valid():
        indicator = form.save()
        from .models import TargetChange

        TargetChange.objects.create(
            indicator=indicator,
            old_value=None,
            new_value=indicator.annual_target,
            reason="Target set",
            changed_by=request.user,
        )
        svc.ensure_monthly(indicator)
        log_event(AuditLog.Action.ADD, request=request, obj=indicator)
        messages.success(request, "Target created and split into monthly targets. Adjust any month below.")
        return redirect("portal:target_detail", pk=indicator.pk)
    return render(request, "portal/targets/form.html", {"form": form})


# ------------------------------------------------------------------------------------------------ detail
def _decimal(raw: str | None) -> Decimal | None:
    try:
        return Decimal((raw or "").replace(",", "").strip()) if (raw or "").strip() else None
    except InvalidOperation:
        return None


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def target_detail(request: HttpRequest, pk: int) -> HttpResponse:
    access = get_access(request)
    indicator = get_object_or_404(visible(access), pk=pk)  # out of scope -> 404
    manage = svc.can_manage(access)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "annual" and manage:
                new = _decimal(request.POST.get("annual_target"))
                if new is None:
                    raise ValidationError("Enter the new annual target.")
                svc.set_annual(request, access, indicator, new, request.POST.get("reason", ""))
                messages.success(request, "Annual target changed and split again into monthly targets.")
            elif action == "months" and manage:
                targets = {}
                for m in range(1, 13):
                    value = _decimal(request.POST.get(f"m{m}"))
                    if value is not None:
                        targets[m] = value
                changed = svc.set_months(request, access, indicator, targets, request.POST.get("reason", ""))
                messages.success(request, f"{changed} monthly target(s) changed.")
            elif action == "actual" and can_record(access, indicator):
                month_raw = request.POST.get("month", "")
                month = int(month_raw) if month_raw.isdigit() and 1 <= int(month_raw) <= 12 else 0
                value = _decimal(request.POST.get("value"))
                if not month or value is None or value < 0:
                    raise ValidationError("Choose a month and enter the actual figure (0 or more).")
                if dt.date(indicator.year, month, 1) > timezone.localdate():
                    raise ValidationError("You cannot record an actual for a month that has not started.")
                svc.record_actual(request, indicator, month, value, request.POST.get("note", ""))
                log_event(
                    AuditLog.Action.CHANGE, request=request, obj=indicator, extra={"actual_month": month}
                )
                messages.success(request, "Actual recorded.")
            else:
                raise PermissionDenied
            return redirect("portal:target_detail", pk=indicator.pk)
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
    if manage:
        svc.ensure_monthly(indicator)
    row = svc.status(indicator, svc.reporting_month(indicator.year))
    months = []
    for m in range(1, 13):
        target = row.targets[m - 1]
        actual = row.trend[m - 1]
        progress = indicator.progress(actual, target) if actual is not None else None
        months.append(
            {
                "number": m,
                "label": dt.date(indicator.year, m, 1).strftime("%b %Y"),
                "target": target,
                "actual": actual,
                "progress": progress,
                "rag": svc.RAG_STATUS.get(svc.rag(progress), ("", "")),
                "overdue": m in row.overdue,
            }
        )
    return render(
        request,
        "portal/targets/detail.html",
        {
            "indicator": indicator,
            "row": row,
            "months": months,
            "history": indicator.target_changes.select_related("changed_by")[:50],
            "can_manage": manage,
            "can_record": can_record(access, indicator),
            "this_month": timezone.localdate().month if indicator.year == timezone.localdate().year else 12,
        },
    )


# ------------------------------------------------------------------------------------------------ import
@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def target_import(request: HttpRequest) -> HttpResponse:
    access = get_access(request)
    if not svc.can_manage(access):
        raise PermissionDenied
    context: dict[str, Any] = {"columns": svc.CSV_COLUMNS, "max_kb": svc.MAX_CSV_BYTES // 1024}
    if request.method == "POST":
        if request.POST.get("confirm") and SESSION_IMPORT in request.session:
            data = base64.b64decode(request.session.pop(SESSION_IMPORT))
            result = svc.import_csv(request, access, data, dry_run=False)
            if result.errors:
                context["result"] = result
            else:
                messages.success(
                    request, f"Imported: {result.created} new target(s), {result.updated} updated."
                )
                return redirect("portal:targets")
        else:
            upload = request.FILES.get("file")
            if upload is None or not upload.name.lower().endswith(".csv"):
                messages.error(request, "Choose a .csv file.")
            elif upload.size > svc.MAX_CSV_BYTES:
                messages.error(request, f"The file is larger than {svc.MAX_CSV_BYTES // 1024} KB.")
            else:
                data = upload.read(svc.MAX_CSV_BYTES + 1)
                result = svc.import_csv(request, access, data, dry_run=True)
                context["result"] = result
                if not result.errors:
                    request.session[SESSION_IMPORT] = base64.b64encode(data).decode()
    return render(request, "portal/targets/import.html", context)


@never_cache
@portal_view()
def target_template(request: HttpRequest) -> HttpResponse:
    if not svc.can_manage(get_access(request)):
        raise PermissionDenied
    response = HttpResponse(svc.template_csv(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="targets-template.csv"'
    return response
