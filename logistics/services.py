"""Procurement workflow (docs/DECISIONS.md D-020).

request (any department) -> submitted -> at least 3 quotations -> Logistics recommends a supplier ->
Finance confirms a budget line of the requesting department -> approved by Logistics head or Founder, never
the requester -> purchase order -> delivery note -> goods received (optionally into inventory) -> closed.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import MIN_QUOTATIONS, DeliveryNote, InventoryItem, PurchaseOrder, PurchaseRequest, Quotation

S = PurchaseRequest.Status


def _number(prefix: str, model: Any, field: str = "number") -> str:
    year = timezone.localdate().year
    count = model.objects.filter(**{f"{field}__startswith": f"{prefix}-{year}-"}).count() + 1
    return f"{prefix}-{year}-{count:05d}"


def _require(status_ok: bool, message: str) -> None:
    if not status_ok:
        raise ValidationError(message)


@transaction.atomic
def submit(request: HttpRequest, pr: PurchaseRequest) -> None:
    _require(pr.status == S.DRAFT, "Only drafts can be submitted.")
    pr.status = S.SUBMITTED
    pr.number = pr.number or _number("PR", PurchaseRequest)
    pr.save()
    log_event(AuditLog.Action.SUBMIT, request=request, obj=pr)


@transaction.atomic
def recommend(request: HttpRequest, pr: PurchaseRequest, quotation: Quotation, note: str) -> None:
    _require(pr.status == S.SUBMITTED, "Quotations can only be compared while the request is open for them.")
    _require(quotation.request_id == pr.pk, "That quotation belongs to another request.")
    count = pr.quotations.count()
    _require(count >= MIN_QUOTATIONS, f"At least {MIN_QUOTATIONS} quotations are needed ({count} so far).")
    cheapest = pr.quotations.order_by("amount").first()
    if cheapest and quotation.pk != cheapest.pk and not note.strip():
        raise ValidationError("You chose a supplier that is not the cheapest: explain why.")
    pr.recommended_quotation = quotation
    pr.recommendation_note = note.strip()[:2000]
    pr.status = S.RECOMMENDED
    pr.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=pr, extra={"recommended": quotation.pk})


@transaction.atomic
def confirm_budget(request: HttpRequest, pr: PurchaseRequest, budget_line: Any) -> None:
    """Finance checks the budget and sends the purchase for EXECUTIVE approval (decision 3).

    ``budget_line`` may be None when the requesting department has no suitable line: the purchase is then
    UNBUDGETED and the approver must justify it. The same happens when the line's remaining balance is too small.
    """
    from finance.approvals import KINDS, check_budget

    _require(pr.status == S.RECOMMENDED, "Finance checks the budget after a supplier is recommended.")
    if budget_line is not None:
        _require(
            budget_line.department_id == pr.requesting_department_id,
            "Use a budget line of the requesting department.",
        )
        _require(budget_line.year == timezone.localdate().year, "Use a budget line of the current year.")
    pr.budget_line = budget_line
    pr.budget_confirmed_by = request.user
    pr.budget_confirmed_at = timezone.now()
    pr.status = S.BUDGET_CONFIRMED
    pr.unbudgeted = check_budget(KINDS["purchase"], pr).unbudgeted
    pr.save()
    log_event(
        AuditLog.Action.SUBMIT,
        request=request,
        obj=pr,
        extra={"budget_line": budget_line.pk if budget_line else None, "unbudgeted": pr.unbudgeted},
    )


@transaction.atomic
def reject(request: HttpRequest, pr: PurchaseRequest, note: str) -> None:
    _require(
        pr.status in (S.SUBMITTED, S.RECOMMENDED, S.BUDGET_CONFIRMED),
        "This request can no longer be rejected.",
    )
    _require(bool(note.strip()), "Give a reason.")
    pr.status = S.REJECTED
    pr.rejection_note = note.strip()[:300]
    pr.save()
    log_event(AuditLog.Action.REJECT, request=request, obj=pr)


@transaction.atomic
def issue_order(request: HttpRequest, pr: PurchaseRequest, expected_delivery: Any = None) -> PurchaseOrder:
    _require(pr.status == S.APPROVED, "Only approved requests get a purchase order.")
    quote = pr.recommended_quotation
    order = PurchaseOrder.objects.create(
        request=pr,
        number=_number("PO", PurchaseOrder),
        supplier=quote.supplier,
        amount=quote.amount,
        issued_by=request.user,
        expected_delivery=expected_delivery
        or (timezone.localdate() + timedelta(days=quote.delivery_days) if quote.delivery_days else None),
    )
    pr.status = S.ORDERED
    pr.save()
    log_event(AuditLog.Action.ADD, request=request, obj=order)
    return order


def delivery_recorded(note: DeliveryNote) -> None:
    """After a complete delivery note: the request becomes 'goods received'."""
    pr = note.order.request
    if note.is_complete and pr.status == S.ORDERED:
        pr.status = S.RECEIVED
        pr.save(update_fields=["status", "updated_at"])


@transaction.atomic
def receive_into_inventory(
    request: HttpRequest, order: PurchaseOrder, *, name: str, quantity: int, kind: str
) -> InventoryItem:
    _require(order.request.status in (S.RECEIVED, S.CLOSED), "Record the delivery first.")
    item = InventoryItem.objects.create(
        name=name,
        quantity=quantity,
        kind=kind,
        purchase_order=order,
        branch=order.request.branch,
        notes=f"Received from {order.number}",
    )
    log_event(AuditLog.Action.ADD, request=request, obj=item, extra={"from_order": order.pk})
    return item


@transaction.atomic
def close(request: HttpRequest, pr: PurchaseRequest) -> None:
    _require(pr.status == S.RECEIVED, "Close after the goods are received.")
    pr.status = S.CLOSED
    pr.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=pr, extra={"closed": True})


def comparison(pr: PurchaseRequest) -> list[dict[str, Any]]:
    """Side-by-side quotation comparison, cheapest first."""
    quotes = list(pr.quotations.select_related("supplier").order_by("amount"))
    cheapest = quotes[0].amount if quotes else None
    return [
        {
            "quotation": q,
            "supplier": q.supplier,
            "rating": q.supplier.rating,
            "amount": q.amount,
            "difference": (q.amount - cheapest) if cheapest is not None else None,
            "delivery_days": q.delivery_days,
            "valid_until": q.valid_until,
            "recommended": pr.recommended_quotation_id == q.pk,
        }
        for q in quotes
    ]
