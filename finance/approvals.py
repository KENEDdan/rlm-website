"""Executive approval of every expenditure and financial commitment (ministry decision 3, DECISIONS D-028).

What needs approval ("kinds"): expenditure entries in the ledger (payments, project payments, reimbursements,
purchase-order payments), purchase requests, campaign / mission-trip budgets, event (logistics plan) budgets and
budget lines themselves. There is no amount below which approval is skipped.

Rules enforced here for every kind (views check too, but these hold even if a view forgets):
* only a current approver (``Approver`` rows managed by the Super Admin; active Super Admins when none exist);
* fresh re-authentication (password + 2FA);
* the requester / recorder / submitter can never approve or reject their own item;
* UNBUDGETED (no approved budget line, or more than its remaining balance) needs a written justification and,
  when Finance settings say so, a reallocation or supplementary budget;
* every decision is stored in the append-only ``ApprovalDecision`` table AND the audit log, and the requester is
  emailed without amounts, names or descriptions.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q, QuerySet, Sum
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import (
    ApprovalDecision,
    Approver,
    BudgetAdjustment,
    BudgetApproval,
    BudgetLine,
    FinanceSettings,
    LedgerEntry,
    year_is_closed,
)

ZERO = Decimal("0")


# ------------------------------------------------------------------------------------------ approvers
def current_approver_rows(on: Any = None) -> QuerySet:
    on = on or timezone.localdate()
    return (
        Approver.objects.filter(is_active=True, user__is_active=True, user__deleted_at__isnull=True)
        .filter(Q(starts_on__isnull=True) | Q(starts_on__lte=on))
        .filter(Q(ends_on__isnull=True) | Q(ends_on__gte=on))
    )


def is_approver(user: Any, on: Any = None) -> bool:
    if not getattr(user, "is_authenticated", False) or not user.is_active:
        return False
    if Approver.objects.filter(is_active=True).exists():
        return current_approver_rows(on).filter(user=user).exists()
    # No approver configured yet: the Super Admins (Founder) approve.
    return bool(getattr(user, "is_super_admin", False))


def approver_role(user: Any) -> str:
    row = current_approver_rows().filter(user=user).first()
    return row.get_role_display() if row else "Super Admin (no approvers configured)"


def approver_emails() -> list[str]:
    users = get_user_model().objects.filter(pk__in=current_approver_rows().values("user"))
    if not Approver.objects.filter(is_active=True).exists():
        users = get_user_model().objects.filter(is_superuser=True, is_active=True, deleted_at__isnull=True)
    return list(users.values_list("email", flat=True))


# ------------------------------------------------------------------------------------------ budget position
@dataclass
class LinePosition:
    budget: Decimal
    adjustments: Decimal
    spent: Decimal
    committed: Decimal

    @property
    def total(self) -> Decimal:
        return self.budget + self.adjustments

    @property
    def remaining(self) -> Decimal:
        return self.total - self.spent - self.committed


def _paid(qs: QuerySet) -> Decimal:
    return (
        qs.filter(status=LedgerEntry.Status.POSTED, kind=LedgerEntry.Kind.EXPENSE).aggregate(t=Sum("amount"))[
            "t"
        ]
        or ZERO
    )


def commitment_unpaid(obj: Any) -> Decimal:
    """Approved amount of a commitment not yet paid through posted ledger entries."""
    from logistics.models import LogisticsPlan, PurchaseRequest
    from missions.models import Campaign

    if isinstance(obj, PurchaseRequest):
        if obj.status not in (
            obj.Status.APPROVED,
            obj.Status.ORDERED,
            obj.Status.RECEIVED,
            obj.Status.CLOSED,
        ):
            return ZERO
        amount = (
            obj.recommended_quotation.amount if obj.recommended_quotation_id else (obj.estimated_cost or ZERO)
        )
        order = getattr(obj, "order", None)
        paid = _paid(LedgerEntry.objects.filter(purchase_order=order)) if order else ZERO
        return max(ZERO, amount - paid)
    if isinstance(obj, Campaign):
        if not obj.budget_is_approved:
            return ZERO
        return max(ZERO, (obj.budget_request or ZERO) - _paid(LedgerEntry.objects.filter(campaign=obj)))
    if isinstance(obj, LogisticsPlan):
        if not obj.budget_is_approved:
            return ZERO
        return max(ZERO, (obj.budget_amount or ZERO) - _paid(LedgerEntry.objects.filter(logistics_plan=obj)))
    return ZERO


def line_position(line: BudgetLine) -> LinePosition:
    from logistics.models import LogisticsPlan, PurchaseRequest
    from missions.models import Campaign

    adjustments = (BudgetAdjustment.objects.filter(to_line=line).aggregate(t=Sum("amount"))["t"] or ZERO) - (
        BudgetAdjustment.objects.filter(from_line=line).aggregate(t=Sum("amount"))["t"] or ZERO
    )
    spent = _paid(LedgerEntry.objects.filter(budget_line=line))
    committed = ZERO
    for pr in PurchaseRequest.objects.filter(budget_line=line).select_related("recommended_quotation"):
        committed += commitment_unpaid(pr)
    for campaign in Campaign.objects.filter(
        budget_line=line, budget_status=BudgetApproval.BudgetStatus.APPROVED
    ):
        committed += commitment_unpaid(campaign)
    for plan in LogisticsPlan.objects.filter(
        budget_line=line, budget_status=BudgetApproval.BudgetStatus.APPROVED
    ):
        committed += commitment_unpaid(plan)
    return LinePosition(budget=line.amount, adjustments=adjustments, spent=spent, committed=committed)


# ------------------------------------------------------------------------------------------ kinds
class Kind:
    code = ""
    label = ""

    def pending(self) -> QuerySet:
        raise NotImplementedError

    def get(self, pk: int) -> Any:
        return self.pending().filter(pk=pk).first()

    def amount(self, obj: Any) -> Decimal:
        raise NotImplementedError

    def reference(self, obj: Any) -> str:
        return f"{self.label} #{obj.pk}"

    def department(self, obj: Any) -> Any:
        return getattr(obj, "department", None)

    def branch(self, obj: Any) -> Any:
        return getattr(obj, "branch", None)

    def requester_ids(self, obj: Any) -> set[int]:
        raise NotImplementedError

    def notify_user(self, obj: Any) -> Any:
        return None

    def budget_line(self, obj: Any) -> BudgetLine | None:
        return getattr(obj, "budget_line", None)

    def set_budget_line(self, obj: Any, line: BudgetLine) -> None:
        obj.budget_line = line

    def covered_by(self, obj: Any) -> Any:
        """An approved commitment this payment belongs to, if any."""
        return None

    def check_open_year(self, obj: Any) -> None:
        return None

    def description(self, obj: Any) -> list[tuple[str, Any]]:
        return []

    def mark_unbudgeted(self, obj: Any, flag: bool) -> None:
        raise NotImplementedError

    def approve(self, obj: Any, user: Any) -> None:
        raise NotImplementedError

    def reject(self, obj: Any, user: Any, note: str) -> None:
        raise NotImplementedError

    def detail_url(self, obj: Any) -> str:
        from django.urls import reverse

        return reverse("portal:finance:approval_detail", args=[self.code, obj.pk])


class ExpenseKind(Kind):
    code, label = "expense", "Expenditure"

    def pending(self) -> QuerySet:
        return LedgerEntry.objects.filter(kind=LedgerEntry.Kind.EXPENSE, status=LedgerEntry.Status.SUBMITTED)

    def amount(self, obj: LedgerEntry) -> Decimal:
        return obj.amount

    def requester_ids(self, obj: LedgerEntry) -> set[int]:
        return {obj.recorded_by_id} if obj.recorded_by_id else set()

    def notify_user(self, obj: LedgerEntry) -> Any:
        return obj.recorded_by

    def covered_by(self, obj: LedgerEntry) -> Any:
        if obj.purchase_order_id:
            return obj.purchase_order.request
        return obj.campaign or obj.logistics_plan

    def check_open_year(self, obj: LedgerEntry) -> None:
        if year_is_closed(obj.date.year):
            raise ValidationError(f"Financial year {obj.date.year} is closed.")

    def description(self, obj: LedgerEntry) -> list[tuple[str, Any]]:
        what = obj.project or obj.purchase_order or obj.campaign or obj.logistics_plan
        return [
            ("Date", obj.date.strftime("%d %b %Y")),
            ("Category", obj.get_category_display() or "—"),
            ("Description", obj.description),
            ("For", str(what) if what else "—"),
            ("Reversal of", obj.reverses.number if obj.reverses_id else "—"),
        ]

    def mark_unbudgeted(self, obj: LedgerEntry, flag: bool) -> None:
        LedgerEntry.objects.filter(pk=obj.pk).update(unbudgeted=flag)
        obj.unbudgeted = flag

    def approve(self, obj: LedgerEntry, user: Any) -> None:
        from .services import _next_number

        obj.status = LedgerEntry.Status.POSTED
        obj.approved_by = user
        obj.posted_at = timezone.now()
        obj.number = _next_number(obj)
        obj.save()

    def reject(self, obj: LedgerEntry, user: Any, note: str) -> None:
        obj.status = LedgerEntry.Status.REJECTED
        obj.rejection_note = note[:300]
        obj.save()


class PurchaseKind(Kind):
    code, label = "purchase", "Purchase request"

    def pending(self) -> QuerySet:
        from logistics.models import PurchaseRequest

        return PurchaseRequest.objects.filter(status=PurchaseRequest.Status.BUDGET_CONFIRMED)

    def amount(self, obj: Any) -> Decimal:
        quote = obj.recommended_quotation
        return quote.amount if quote else (obj.estimated_cost or ZERO)

    def reference(self, obj: Any) -> str:
        return obj.number or f"Purchase request #{obj.pk}"

    def department(self, obj: Any) -> Any:
        return obj.requesting_department

    def requester_ids(self, obj: Any) -> set[int]:
        return {i for i in (obj.requested_by_id, obj.budget_confirmed_by_id) if i}

    def notify_user(self, obj: Any) -> Any:
        return obj.requested_by

    def description(self, obj: Any) -> list[tuple[str, Any]]:
        quote = obj.recommended_quotation
        return [
            ("Title", obj.title),
            ("Requesting department", obj.requesting_department),
            ("Recommended supplier", f"{quote.supplier} ({quote.amount:,.2f})" if quote else "—"),
            ("Why this supplier", obj.recommendation_note or "Cheapest of the quotations"),
            ("Quotations received", obj.quotations.count()),
        ]

    def mark_unbudgeted(self, obj: Any, flag: bool) -> None:
        type(obj).objects.filter(pk=obj.pk).update(unbudgeted=flag)
        obj.unbudgeted = flag

    def approve(self, obj: Any, user: Any) -> None:
        obj.status = obj.Status.APPROVED
        obj.approved_by = user
        obj.approved_at = timezone.now()
        obj.save()

    def reject(self, obj: Any, user: Any, note: str) -> None:
        obj.status = obj.Status.REJECTED
        obj.rejection_note = note[:300]
        obj.save()


class _BudgetKind(Kind):
    """Campaign / mission trip and event budgets (models using ``BudgetApproval``)."""

    def requester_ids(self, obj: Any) -> set[int]:
        return {obj.budget_submitted_by_id} if obj.budget_submitted_by_id else set()

    def notify_user(self, obj: Any) -> Any:
        return obj.budget_submitted_by

    def mark_unbudgeted(self, obj: Any, flag: bool) -> None:
        type(obj).objects.filter(pk=obj.pk).update(budget_unbudgeted=flag)
        obj.budget_unbudgeted = flag

    def approve(self, obj: Any, user: Any) -> None:
        obj.budget_status = BudgetApproval.BudgetStatus.APPROVED
        obj.budget_approved_by = user
        obj.budget_approved_at = timezone.now()
        obj.budget_decision_note = ""
        obj.save()

    def reject(self, obj: Any, user: Any, note: str) -> None:
        obj.budget_status = BudgetApproval.BudgetStatus.REJECTED
        obj.budget_decision_note = note[:300]
        obj.save()


class CampaignKind(_BudgetKind):
    code, label = "campaign", "Outreach / mission trip budget"

    def pending(self) -> QuerySet:
        from missions.models import Campaign

        return Campaign.objects.filter(budget_status=BudgetApproval.BudgetStatus.SUBMITTED)

    def amount(self, obj: Any) -> Decimal:
        return obj.budget_request or ZERO

    def department(self, obj: Any) -> Any:
        from portal.models import Department

        return Department.objects.filter(code="missions").first()

    def description(self, obj: Any) -> list[tuple[str, Any]]:
        return [
            ("Campaign", obj.title),
            ("Type", obj.get_kind_display()),
            (
                "Dates",
                f"{obj.start_date:%d %b %Y}" + (f" to {obj.end_date:%d %b %Y}" if obj.end_date else ""),
            ),
            ("Location", obj.location or obj.community or "—"),
            ("Materials", obj.materials or "—"),
        ]

    def approve(self, obj: Any, user: Any) -> None:
        if obj.status == obj.Status.PLANNED:
            obj.status = obj.Status.APPROVED
        super().approve(obj, user)


class EventBudgetKind(_BudgetKind):
    code, label = "event_budget", "Event budget"

    def pending(self) -> QuerySet:
        from logistics.models import LogisticsPlan

        return LogisticsPlan.objects.filter(budget_status=BudgetApproval.BudgetStatus.SUBMITTED)

    def amount(self, obj: Any) -> Decimal:
        return obj.budget_amount or ZERO

    def department(self, obj: Any) -> Any:
        from portal.models import Department

        return Department.objects.filter(code="logistics").first()

    def description(self, obj: Any) -> list[tuple[str, Any]]:
        return [
            ("Event", obj.title),
            ("Type", obj.get_kind_display()),
            ("Starts", obj.start_date.strftime("%d %b %Y")),
            ("Expected attendance", obj.expected_attendance or "—"),
            ("Checklist estimate", f"{sum((t.estimated_cost or ZERO) for t in obj.tasks.all()):,.2f}"),
        ]


class BudgetLineKind(Kind):
    code, label = "budget_line", "Budget line"

    def pending(self) -> QuerySet:
        return BudgetLine.objects.filter(status=BudgetLine.Status.SUBMITTED)

    def amount(self, obj: BudgetLine) -> Decimal:
        return obj.amount

    def requester_ids(self, obj: BudgetLine) -> set[int]:
        return {obj.submitted_by_id} if obj.submitted_by_id else set()

    def notify_user(self, obj: BudgetLine) -> Any:
        return obj.submitted_by

    def budget_line(self, obj: BudgetLine) -> BudgetLine | None:
        return None  # a budget line is the budget; it is never "unbudgeted"

    def description(self, obj: BudgetLine) -> list[tuple[str, Any]]:
        return [("Year", obj.year), ("Line", obj.name), ("Category", obj.get_category_display())]

    def mark_unbudgeted(self, obj: BudgetLine, flag: bool) -> None:
        return None

    def approve(self, obj: BudgetLine, user: Any) -> None:
        obj.status = BudgetLine.Status.APPROVED
        obj.approved_by = user
        obj.approved_at = timezone.now()
        obj.save()

    def reject(self, obj: BudgetLine, user: Any, note: str) -> None:
        obj.status = BudgetLine.Status.REJECTED
        obj.notes = (obj.notes + f"\nNot approved: {note}").strip()[:2000]
        obj.save()


KINDS: dict[str, Kind] = {
    k.code: k for k in (ExpenseKind(), PurchaseKind(), CampaignKind(), EventBudgetKind(), BudgetLineKind())
}


# ------------------------------------------------------------------------------------------ budget check
@dataclass
class BudgetCheck:
    unbudgeted: bool
    reason: str
    position: LinePosition | None
    shortfall: Decimal = ZERO


def check_budget(kind: Kind, obj: Any) -> BudgetCheck:
    if isinstance(kind, BudgetLineKind):
        return BudgetCheck(False, "", None)
    amount = kind.amount(obj)
    covering = kind.covered_by(obj)
    if covering is not None:
        unpaid = commitment_unpaid(covering)
        if unpaid >= amount:
            return BudgetCheck(False, f"Within the approved commitment ({covering}).", None)
        if unpaid > ZERO:
            return BudgetCheck(
                True,
                f"More than what is left of the approved commitment ({unpaid:,.2f}).",
                None,
                amount - unpaid,
            )
    line = kind.budget_line(obj)
    if line is None:
        return BudgetCheck(True, "No budget line was chosen.", None, amount)
    if line.status != BudgetLine.Status.APPROVED:
        return BudgetCheck(True, "The budget line is not approved.", line_position(line), amount)
    position = line_position(line)
    if amount > position.remaining:
        return BudgetCheck(
            True,
            f"More than the remaining balance of the budget line ({position.remaining:,.2f}).",
            position,
            amount - max(position.remaining, ZERO),
        )
    return BudgetCheck(False, "", position)


def pending_items() -> list[dict[str, Any]]:
    items = []
    for kind in KINDS.values():
        for obj in kind.pending():
            check = check_budget(kind, obj)
            items.append(
                {
                    "kind": kind,
                    "obj": obj,
                    "amount": kind.amount(obj),
                    "reference": kind.reference(obj),
                    "department": kind.department(obj),
                    "unbudgeted": check.unbudgeted,
                    "reason": check.reason,
                    "url": kind.detail_url(obj),
                }
            )
    items.sort(key=lambda i: (not i["unbudgeted"], -i["amount"]))
    return items


def unbudgeted_summary() -> dict[str, Any]:
    items = [i for i in pending_items() if i["unbudgeted"]]
    return {"count": len(items), "total": sum((i["amount"] for i in items), ZERO)}


# ------------------------------------------------------------------------------------------ decisions
def _authorise(request: HttpRequest, kind: Kind, obj: Any) -> None:
    from accounts import reauth

    user = request.user
    if not is_approver(user):
        raise PermissionDenied(
            "Only an approver (Founder, Executive Director or acting approver) can decide this."
        )
    if not reauth.is_fresh(request):
        raise reauth.ReauthRequired
    if user.pk in kind.requester_ids(obj):
        raise PermissionDenied(
            "You asked for, recorded or checked this yourself, so another approver must decide."
        )


def _record(request: HttpRequest, kind: Kind, obj: Any, decision: str, check: BudgetCheck, note: str) -> None:
    override = decision == ApprovalDecision.Decision.APPROVED and check.unbudgeted
    ApprovalDecision.objects.create(
        kind=kind.code,
        object_id=obj.pk,
        reference=kind.reference(obj)[:120],
        department=kind.department(obj),
        amount=kind.amount(obj),
        decision=decision,
        unbudgeted=check.unbudgeted,
        override=override,
        justification=note,
        approver=request.user,
        approver_role=approver_role(request.user),
    )
    log_event(
        AuditLog.Action.APPROVE if decision == ApprovalDecision.Decision.APPROVED else AuditLog.Action.REJECT,
        request=request,
        obj=obj,
        extra={
            "kind": kind.code,
            "unbudgeted": check.unbudgeted,
            "override": override,
            "executive_approval": True,
        },
    )
    recipient = kind.notify_user(obj)
    if recipient is not None and recipient.email and recipient.is_active:
        context = {
            "label": kind.label,
            "reference": f"{kind.label} #{obj.pk}",
            "approved": decision == "approved",
            "site_url": settings.SITE_URL,
        }
        transaction.on_commit(
            lambda: send_mail(
                subject=render_to_string("emails/approval_decision_subject.txt", context).strip(),
                message=render_to_string("emails/approval_decision.txt", context),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[recipient.email],
            )
        )


@transaction.atomic
def approve(
    request: HttpRequest,
    kind_code: str,
    pk: int,
    *,
    justification: str = "",
    adjustment: dict[str, Any] | None = None,
) -> Any:
    kind = KINDS[kind_code]
    obj = kind.pending().select_for_update().filter(pk=pk).first()
    if obj is None:
        raise ValidationError("This item is no longer waiting for approval.")
    _authorise(request, kind, obj)
    kind.check_open_year(obj)
    check = check_budget(kind, obj)
    justification = (justification or "").strip()
    if check.unbudgeted:
        if not justification:
            raise ValidationError("UNBUDGETED: a written justification is required to approve this.")
        if adjustment and adjustment.get("kind"):
            _apply_adjustment(request, kind, obj, check, adjustment, justification)
        elif FinanceSettings.load().unbudgeted_requires_adjustment:
            raise ValidationError(
                "UNBUDGETED: Finance settings require a budget reallocation or a supplementary budget for the shortfall."
            )
    kind.mark_unbudgeted(obj, check.unbudgeted)
    kind.approve(obj, request.user)
    _record(request, kind, obj, ApprovalDecision.Decision.APPROVED, check, justification)
    return obj


@transaction.atomic
def reject(request: HttpRequest, kind_code: str, pk: int, *, reason: str) -> Any:
    kind = KINDS[kind_code]
    obj = kind.pending().select_for_update().filter(pk=pk).first()
    if obj is None:
        raise ValidationError("This item is no longer waiting for approval.")
    _authorise(request, kind, obj)
    if not (reason or "").strip():
        raise ValidationError("Give the reason, so the requester knows what to change.")
    check = check_budget(kind, obj)
    kind.reject(obj, request.user, reason.strip())
    _record(request, kind, obj, ApprovalDecision.Decision.REJECTED, check, reason.strip())
    return obj


def _apply_adjustment(
    request: HttpRequest,
    kind: Kind,
    obj: Any,
    check: BudgetCheck,
    adjustment: dict[str, Any],
    justification: str,
) -> None:
    to_line = adjustment.get("to_line") or kind.budget_line(obj)
    if to_line is None:
        raise ValidationError("Choose the budget line to adjust.")
    if to_line.status != BudgetLine.Status.APPROVED:
        raise ValidationError("Only an approved budget line can be adjusted.")
    if year_is_closed(to_line.year):
        raise ValidationError(f"Financial year {to_line.year} is closed.")
    amount = adjustment.get("amount") or check.shortfall
    if amount < check.shortfall:
        raise ValidationError(f"The adjustment must cover the shortfall of {check.shortfall:,.2f}.")
    from_line = None
    if adjustment["kind"] == BudgetAdjustment.Kind.REALLOCATION:
        from_line = adjustment.get("from_line")
        if from_line is None or from_line.pk == to_line.pk:
            raise ValidationError("Choose another budget line to take the money from.")
        if from_line.status != BudgetLine.Status.APPROVED or line_position(from_line).remaining < amount:
            raise ValidationError("That budget line does not have enough remaining balance to reallocate.")
    adjustment_obj = BudgetAdjustment.objects.create(
        kind=adjustment["kind"],
        from_line=from_line,
        to_line=to_line,
        amount=amount,
        justification=justification,
        approved_by=request.user,
    )
    if kind.budget_line(obj) is None:
        kind.set_budget_line(obj, to_line)
        obj.save()
    log_event(
        AuditLog.Action.APPROVE,
        request=request,
        obj=adjustment_obj,
        extra={"budget_adjustment": adjustment["kind"]},
    )


# ------------------------------------------------------------------------------------------ submissions
@transaction.atomic
def submit_budget(request: HttpRequest, obj: Any, amount: Decimal | None) -> None:
    """A department submits a campaign / mission-trip / event budget for executive approval."""
    if not amount or amount <= ZERO:
        raise ValidationError("Enter the budget amount first (Edit).")
    if obj.budget_status not in (
        BudgetApproval.BudgetStatus.NOT_SUBMITTED,
        BudgetApproval.BudgetStatus.REJECTED,
    ):
        raise ValidationError("This budget was already submitted.")
    obj.budget_status = BudgetApproval.BudgetStatus.SUBMITTED
    obj.budget_submitted_by = request.user
    obj.budget_decision_note = ""
    obj.save()
    log_event(AuditLog.Action.SUBMIT, request=request, obj=obj, extra={"budget": str(amount)})


@transaction.atomic
def submit_budget_line(request: HttpRequest, line: BudgetLine) -> None:
    if line.status not in (BudgetLine.Status.DRAFT, BudgetLine.Status.REJECTED):
        raise ValidationError("This budget line was already submitted.")
    line.status = BudgetLine.Status.SUBMITTED
    line.submitted_by = request.user
    line.save()
    log_event(AuditLog.Action.SUBMIT, request=request, obj=line)
