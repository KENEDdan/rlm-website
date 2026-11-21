"""Executive Finance page (ministry decision 1): summaries only, for Executive Leadership, Founder and Finance."""

from __future__ import annotations

from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache

from audit.models import AuditLog
from audit.services import log_event
from portal.access import get_access, portal_view
from portal.dashboards import PERIOD_CHOICES, financial_years, read_filters
from portal.views import is_htmx

from . import executive


@never_cache
@portal_view()
def executive_finance(request: HttpRequest) -> HttpResponse:
    access = get_access(request)
    if not executive.can_view(access):
        raise PermissionDenied
    filters = read_filters(request, access, "finance")
    data = executive.summary(filters, department_code=request.GET.get("department", "")[:40])
    log_event(AuditLog.Action.VIEW, request=request, extra={"page": "executive finance", "fy": data["year"]})
    context = {
        "data": data,
        "query": urlencode(filters.as_query()),
        "filters": filters,
        "fy_choices": financial_years(),
        "period_choices": PERIOD_CHOICES,
        "branches": (
            access.allowed_branches("finance") if not access.is_executive else access.allowed_branches()
        ),
        "branch_fixed": access.branch_restricted_in("finance") and not access.is_executive,
    }
    if is_htmx(request):
        return render(request, "finance/executive/_body.html", context)
    return render(request, "finance/executive/page.html", context)


@never_cache
@portal_view()
def executive_finance_print(request: HttpRequest) -> HttpResponse:
    """Printable Executive Finance summary (decision 7): confidential, summaries only."""
    from django.urls import reverse

    from portal.printing import print_context

    access = get_access(request)
    if not executive.can_view(access):
        raise PermissionDenied
    filters = read_filters(request, access, "finance")
    data = executive.summary(filters, department_code=request.GET.get("department", "")[:40])
    context = {
        "data": data,
        "filters": filters,
        **print_context(
            request,
            title="Executive finance summary",
            department="Finance & Resource Mobilization (summaries only)",
            branch=filters.branch_name,
            start=filters.start,
            end=filters.end,
            period_label=f"{filters.period_label}: {filters.start:%d %b %Y} to {filters.end:%d %b %Y}",
            fy=filters.fy,
            sensitive=True,
            back_url=reverse("portal:finance:executive_finance"),
        ),
    }
    return render(request, "print/executive_finance.html", context)
