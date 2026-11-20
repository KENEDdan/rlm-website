"""Executive approval screens: the inbox and one decision page per item (ministry decision 3)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts import reauth
from portal.access import get_access, portal_view

from . import approvals
from .models import ApprovalDecision, BudgetAdjustment, BudgetLine, FinanceSettings


def _can_view(request: HttpRequest) -> bool:
    return approvals.is_approver(request.user) or get_access(request).is_super_admin


@never_cache
@portal_view()
def inbox(request: HttpRequest) -> HttpResponse:
    if not _can_view(request):
        raise PermissionDenied
    items = approvals.pending_items()
    context = {
        "items": items,
        "unbudgeted": [i for i in items if i["unbudgeted"]],
        "can_decide": approvals.is_approver(request.user),
        "recent": ApprovalDecision.objects.select_related("approver", "department")[:15],
    }
    return render(request, "finance/approvals/inbox.html", context)


def _decimal(raw: str | None) -> Decimal | None:
    try:
        return Decimal((raw or "").replace(",", "")) if raw else None
    except InvalidOperation:
        return None


def _line(raw: str | None) -> BudgetLine | None:
    return BudgetLine.objects.filter(pk=int(raw)).first() if raw and raw.isdigit() else None


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def detail(request: HttpRequest, kind: str, pk: int) -> HttpResponse:
    if not _can_view(request) or kind not in approvals.KINDS:
        raise PermissionDenied if kind in approvals.KINDS else Http404
    kind_obj = approvals.KINDS[kind]
    obj = kind_obj.get(pk)
    if obj is None:
        messages.info(request, "This item is no longer waiting for approval.")
        return redirect("portal:finance:approvals")
    if request.method == "POST":
        try:
            if request.POST.get("decision") == "approve":
                adjustment: dict[str, Any] | None = None
                if request.POST.get("adjustment") in BudgetAdjustment.Kind.values:
                    adjustment = {
                        "kind": request.POST["adjustment"],
                        "from_line": _line(request.POST.get("from_line")),
                        "to_line": _line(request.POST.get("to_line")),
                        "amount": _decimal(request.POST.get("adjustment_amount")),
                    }
                approvals.approve(
                    request,
                    kind,
                    pk,
                    justification=request.POST.get("justification", ""),
                    adjustment=adjustment,
                )
                messages.success(
                    request, f"Approved: {kind_obj.reference(obj)}. The requester has been told."
                )
            else:
                approvals.reject(request, kind, pk, reason=request.POST.get("justification", ""))
                messages.success(
                    request, f"Not approved: {kind_obj.reference(obj)}. The requester has been told."
                )
            return redirect("portal:finance:approvals")
        except reauth.ReauthRequired:
            here = reverse("portal:finance:approval_detail", args=[kind, pk])
            return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': here})}")
        except (ValidationError, PermissionDenied) as exc:
            messages.error(request, " ".join(getattr(exc, "messages", [])) or str(exc))
    check = approvals.check_budget(kind_obj, obj)
    line = kind_obj.budget_line(obj)
    context = {
        "kind": kind_obj,
        "obj": obj,
        "amount": kind_obj.amount(obj),
        "reference": kind_obj.reference(obj),
        "department": kind_obj.department(obj),
        "branch": kind_obj.branch(obj),
        "rows": kind_obj.description(obj),
        "check": check,
        "line": line,
        "position": approvals.line_position(line) if line else None,
        "approved_lines": BudgetLine.objects.filter(status=BudgetLine.Status.APPROVED).select_related(
            "department"
        ),
        "requires_adjustment": FinanceSettings.load().unbudgeted_requires_adjustment,
        "can_decide": approvals.is_approver(request.user)
        and request.user.pk not in kind_obj.requester_ids(obj),
        "is_own": request.user.pk in kind_obj.requester_ids(obj),
        "fresh": reauth.is_fresh(request),
    }
    return render(request, "finance/approvals/detail.html", context)
