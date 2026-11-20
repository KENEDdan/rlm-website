"""Finance workflow screens, plus the budget page every department sees for ITSELF only."""

from __future__ import annotations

from decimal import Decimal

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Sum
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from accounts.reauth import require_reauth
from audit.models import AuditLog
from audit.services import log_event
from portal.access import DEPARTMENT_ORDER, HEAD, MEMBER, get_access, portal_view
from portal.views import post_action

from . import services
from .models import BudgetLine, LedgerEntry
from .portal_config import DEPT, DonorResource, LedgerResource, VolunteerResource


def _fail(request: HttpRequest, exc: Exception) -> None:
    text = " ".join(getattr(exc, "messages", [])) or (exc.args[0] if exc.args else "Not allowed.")
    messages.error(request, text)


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["GET", "POST"])
def ledger_step(request: HttpRequest, pk: int, step: str) -> HttpResponse:
    access = get_access(request)
    resource, entry = post_action(request, DEPT, "ledger", pk, "view")
    if step not in ("submit", "approve", "reject", "reverse"):
        raise Http404
    if step == "reverse" and not access.is_head(DEPT):
        raise PermissionDenied
    if step == "submit" and not (entry.recorded_by_id == request.user.pk or access.is_head(DEPT)):
        raise PermissionDenied
    if request.method == "GET":
        if step not in ("reject", "reverse"):
            return redirect(resource.url("detail", entry))
        return render(request, "finance/ledger_note.html", {"department": DEPT, "entry": entry, "step": step})
    try:
        if step == "submit":
            services.submit(request, entry)
            messages.success(request, "Submitted. Someone else must now approve it.")
        elif step == "approve":
            services.approve(request, entry)
            messages.success(request, "Approved and posted.")
        elif step == "reject":
            services.reject(request, entry, request.POST.get("note", ""))
            messages.success(request, "Rejected and returned to the person who recorded it.")
        else:
            mirror = services.reverse(request, entry, request.POST.get("note", ""))
            messages.success(request, "Reversing entry created. Someone other than you must approve it.")
            return redirect(resource.url("detail", mirror))
    except (ValidationError, PermissionDenied) as exc:
        _fail(request, exc)
    return redirect(resource.url("detail", entry))


@never_cache
@portal_view(DEPT, level=HEAD)
@require_POST
def year_close(request: HttpRequest, pk: int) -> HttpResponse:
    resource, fy = post_action(request, DEPT, "financial-years", pk, "view")
    try:
        services.close_year(request, fy)
    except ValidationError as exc:
        _fail(request, exc)
    else:
        messages.success(request, f"{fy} is closed.")
    return redirect(resource.url("detail", fy))


@never_cache
@portal_view(super_admin=True)
@require_reauth("portal:home")
@require_http_methods(["GET", "POST"])
def year_reopen(request: HttpRequest, pk: int) -> HttpResponse:
    resource, fy = post_action(request, DEPT, "financial-years", pk, "view")
    if request.method == "POST":
        try:
            services.reopen_year(request, fy, request.POST.get("note", ""))
        except ValidationError as exc:
            _fail(request, exc)
        else:
            messages.success(request, f"{fy} is open again. This was recorded in the audit log.")
            return redirect(resource.url("detail", fy))
    return render(request, "finance/year_reopen.html", {"department": DEPT, "fy": fy})


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def donation_confirm(request: HttpRequest, pk: int) -> HttpResponse:
    resource, donation = post_action(request, DEPT, "donations", pk, "view")
    try:
        entry = services.confirm_donation(request, donation)
    except ValidationError as exc:
        _fail(request, exc)
        return redirect(resource.url("detail", donation))
    messages.success(request, "Donation confirmed. The income entry now needs approval by someone else.")
    return redirect(LedgerResource().url("detail", entry))


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def enquiry_to_donor(request: HttpRequest, pk: int) -> HttpResponse:
    _resource, enquiry = post_action(request, DEPT, "partner-registrations", pk, "view")
    donor = services.donor_from_enquiry(enquiry)
    log_event(AuditLog.Action.ADD, request=request, obj=donor, extra={"from_enquiry": enquiry.pk})
    messages.success(request, "Added to the donor pipeline as a prospect.")
    return redirect(DonorResource().url("detail", donor))


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def volunteer_step(request: HttpRequest, pk: int, step: str) -> HttpResponse:
    access = get_access(request)
    _resource, volunteer = post_action(request, DEPT, "volunteers", pk, "change")
    if step in ("approve", "decline") and not access.is_head(DEPT):
        raise PermissionDenied
    try:
        services.volunteer_step(request, volunteer, step)
    except ValidationError as exc:
        _fail(request, exc)
    else:
        messages.success(request, "Updated.")
    return redirect(VolunteerResource().url("detail", volunteer))


@never_cache
@portal_view(DEPT, level=MEMBER)
def donor_report(request: HttpRequest, pk: int) -> HttpResponse:
    _resource, donor = post_action(request, DEPT, "donors", pk, "view")
    log_event(AuditLog.Action.EXPORT, request=request, obj=donor, extra={"accountability_report": True})
    pledges = donor.pledges.all()
    context = {
        "department": DEPT,
        "donor": donor,
        "pledges": pledges,
        "pledged": pledges.aggregate(t=Sum("amount"))["t"] or Decimal("0"),
        "received": pledges.aggregate(t=Sum("received_amount"))["t"] or Decimal("0"),
        "proposals": donor.proposals.all(),
        "now": timezone.now(),
    }
    return render(request, "finance/donor_report.html", context)


@never_cache
@portal_view(level=MEMBER)
def department_budget(request: HttpRequest, department: str) -> HttpResponse:
    """A department's own budget and spend TOTALS. Never any ledger rows, donors or other departments."""
    if department not in DEPARTMENT_ORDER:
        raise Http404
    try:
        year = int(request.GET.get("year", timezone.localdate().year))
    except ValueError:
        year = timezone.localdate().year
    access = get_access(request)
    # A single-branch assignment sees only its branch's budget lines and spending (D-026).
    lines = access.restrict_branch(BudgetLine.objects.all(), "branch", department)
    entries = access.restrict_branch(LedgerEntry.objects.all(), "branch", department)
    rows = services.budget_vs_actual(year, department, lines=lines, entries=entries)
    budget = sum((r["budget"] for r in rows), Decimal("0"))
    actual = sum((r["actual"] for r in rows), Decimal("0"))
    pending = entries.filter(
        department__code=department, kind="expense", status="submitted", date__year=year
    ).aggregate(t=Sum("amount"))["t"] or Decimal("0")
    context = {
        "department": department,
        "year": year,
        "rows": rows,
        "budget": budget,
        "actual": actual,
        "remaining": budget - actual,
        "percent": int(actual * 100 / budget) if budget else None,
        "pending": pending,
    }
    return render(request, "finance/department_budget.html", context)
