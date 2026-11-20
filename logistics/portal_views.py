"""Procurement workflow screens."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from finance.models import BudgetLine
from portal.access import MEMBER, get_access, portal_view
from portal.views import post_action

from . import services
from .models import InventoryItem
from .portal_config import DEPT, InventoryResource, OrderResource, ProcurementBudgetResource


def _fail(request: HttpRequest, exc: Exception) -> None:
    messages.error(
        request, " ".join(getattr(exc, "messages", [])) or (exc.args[0] if exc.args else "Not allowed.")
    )


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def request_step(request: HttpRequest, pk: int, step: str) -> HttpResponse:
    """submit (requester or Logistics) | reject (Logistics head) | order | close.

    Approval itself is executive approval (Founder / Executive Director) under Approvals (decision 3).
    """
    access = get_access(request)
    resource, pr = post_action(request, DEPT, "requests", pk, "view")
    logistics = resource.effective_level(access) >= MEMBER
    if step == "submit":
        if not (logistics or pr.requested_by_id == request.user.pk):
            raise PermissionDenied
    elif step == "reject":
        if not access.is_head(DEPT):
            raise PermissionDenied
    elif step in ("order", "close"):
        if not logistics:
            raise PermissionDenied
    else:
        raise Http404
    if request.method == "GET":
        if step != "reject":
            return redirect(resource.url("detail", pr))
        return render(request, "logistics/reject.html", {"department": DEPT, "pr": pr})
    try:
        if step == "submit":
            services.submit(request, pr)
        elif step == "reject":
            services.reject(request, pr, request.POST.get("note", ""))
        elif step == "order":
            order = services.issue_order(request, pr)
            messages.success(request, f"Purchase order {order.number} issued.")
            return redirect(OrderResource().url("detail", order))
        else:
            services.close(request, pr)
    except (ValidationError, PermissionDenied) as exc:
        _fail(request, exc)
    else:
        messages.success(request, "Done.")
    return redirect(resource.url("detail", pr))


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["POST"])
def recommend(request: HttpRequest, pk: int) -> HttpResponse:
    resource, pr = post_action(request, DEPT, "requests", pk, "view")
    quotation = get_object_or_404(pr.quotations, pk=request.POST.get("quotation") or 0)
    try:
        services.recommend(request, pr, quotation, request.POST.get("note", ""))
    except ValidationError as exc:
        _fail(request, exc)
    else:
        messages.success(request, "Supplier recommended. Finance will now confirm the budget.")
    return redirect(resource.url("detail", pr))


class BudgetForm(forms.Form):
    budget_line = forms.ModelChoiceField(
        queryset=BudgetLine.objects.none(),
        required=False,
        empty_label="No suitable budget line (UNBUDGETED: the approver must justify it)",
    )


@never_cache
@portal_view("finance", level=MEMBER)
@require_http_methods(["GET", "POST"])
def confirm_budget(request: HttpRequest, pk: int) -> HttpResponse:
    _resource, pr = post_action(request, "finance", "procurement", pk, "view")
    form = BudgetForm(request.POST or None)
    form.fields["budget_line"].queryset = BudgetLine.objects.filter(
        department=pr.requesting_department, year=timezone.localdate().year, status=BudgetLine.Status.APPROVED
    )
    if request.method == "POST" and form.is_valid():
        try:
            services.confirm_budget(request, pr, form.cleaned_data["budget_line"])
        except ValidationError as exc:
            _fail(request, exc)
        else:
            messages.success(request, "Budget checked. The purchase now waits for executive approval.")
            return redirect(ProcurementBudgetResource().url("detail", pr))
    return render(
        request,
        "logistics/confirm_budget.html",
        {"department": "finance", "pr": pr, "form": form, "comparison": services.comparison(pr)},
    )


class ReceiveForm(forms.Form):
    name = forms.CharField(max_length=160)
    quantity = forms.IntegerField(min_value=1, initial=1)
    kind = forms.ChoiceField(choices=InventoryItem.Kind.choices)


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["GET", "POST"])
def receive(request: HttpRequest, pk: int) -> HttpResponse:
    _resource, order = post_action(request, DEPT, "orders", pk, "view")
    form = ReceiveForm(request.POST or None, initial={"name": order.request.title})
    if request.method == "POST" and form.is_valid():
        try:
            item = services.receive_into_inventory(request, order, **form.cleaned_data)
        except ValidationError as exc:
            _fail(request, exc)
        else:
            messages.success(request, "Added to inventory.")
            return redirect(InventoryResource().url("detail", item))
    return render(request, "logistics/receive.html", {"department": DEPT, "order": order, "form": form})


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_http_methods(["POST"])
def plan_budget_submit(request: HttpRequest, pk: int) -> HttpResponse:
    from finance.approvals import submit_budget

    resource, plan = post_action(request, DEPT, "event-logistics", pk, "change")
    try:
        submit_budget(request, plan, plan.budget_amount)
    except ValidationError as exc:
        _fail(request, exc)
    else:
        messages.success(request, "Event budget submitted for executive approval.")
    return redirect(resource.url("detail", plan))
