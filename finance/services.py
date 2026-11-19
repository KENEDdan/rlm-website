"""Finance controls and resource-mobilization services."""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet, Sum
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import BudgetLine, Donor, FinanceSettings, FinanceVolunteer, LedgerEntry

E = LedgerEntry.Status
ZERO = Decimal("0")


# ------------------------------------------------------------------------------------------ ledger workflow
def can_approve(user: Any, entry: LedgerEntry) -> tuple[bool, str]:
    """Segregation of duties + threshold. Returns (allowed, reason when not)."""
    if entry.status != E.SUBMITTED:
        return False, "Only entries awaiting approval can be approved."
    if entry.recorded_by_id == user.pk:
        return False, "You recorded this entry, so someone else must approve it."
    threshold = FinanceSettings.load().approval_threshold
    if abs(entry.amount) > threshold and not getattr(user, "is_super_admin", False):
        return False, f"Entries above {threshold:,.2f} must be approved by the Founder (Super Admin)."
    return True, ""


def _next_number(entry: LedgerEntry) -> str:
    prefix = "RV" if entry.is_reversal else ("IN" if entry.kind == LedgerEntry.Kind.INCOME else "EX")
    year = entry.date.year
    count = LedgerEntry.objects.filter(number__startswith=f"{prefix}-{year}-").count() + 1
    return f"{prefix}-{year}-{count:05d}"


@transaction.atomic
def submit(request: HttpRequest, entry: LedgerEntry) -> None:
    if entry.status not in (E.DRAFT, E.REJECTED):
        raise ValidationError("Only drafts can be submitted.")
    entry.full_clean()
    entry.status = E.SUBMITTED
    entry.submitted_at = timezone.now()
    entry.rejection_note = ""
    entry.save()
    log_event(AuditLog.Action.SUBMIT, request=request, obj=entry)


@transaction.atomic
def approve(request: HttpRequest, entry: LedgerEntry) -> None:
    entry = LedgerEntry.objects.select_for_update().get(pk=entry.pk)
    allowed, reason = can_approve(request.user, entry)
    if not allowed:
        raise PermissionDenied(reason)
    entry.status = E.POSTED
    entry.approved_by = request.user
    entry.posted_at = timezone.now()
    entry.number = _next_number(entry)
    entry.save()
    log_event(AuditLog.Action.POST, request=request, obj=entry, extra={"number": entry.number})


@transaction.atomic
def reject(request: HttpRequest, entry: LedgerEntry, note: str) -> None:
    if entry.status != E.SUBMITTED:
        raise ValidationError("Only entries awaiting approval can be rejected.")
    if entry.recorded_by_id == request.user.pk:
        raise PermissionDenied("You cannot reject your own entry; edit or delete the draft instead.")
    if not note.strip():
        raise ValidationError("Give a reason so the person who recorded it can correct it.")
    entry.status = E.REJECTED
    entry.rejection_note = note.strip()[:300]
    entry.save()
    log_event(AuditLog.Action.REJECT, request=request, obj=entry)


@transaction.atomic
def reverse(request: HttpRequest, entry: LedgerEntry, reason: str) -> LedgerEntry:
    """Correct a posted entry: a negative mirror entry, submitted for approval by someone else."""
    if entry.status != E.POSTED or entry.is_reversal:
        raise ValidationError("Only posted, original entries can be reversed.")
    if LedgerEntry.objects.filter(reverses=entry).exists():
        raise ValidationError("This entry has already been reversed.")
    if not reason.strip():
        raise ValidationError("Give the reason for the correction.")
    mirror = LedgerEntry.objects.create(
        kind=entry.kind,
        date=timezone.localdate(),
        amount=-entry.amount,
        currency=entry.currency,
        department=entry.department,
        budget_line=entry.budget_line,
        category=entry.category,
        income_source=entry.income_source,
        description=f"Reversal of {entry.number}: {reason.strip()[:200]}",
        counterparty=entry.counterparty,
        reference=entry.number or "",
        reverses=entry,
        recorded_by=request.user,
        status=E.SUBMITTED,
        submitted_at=timezone.now(),
    )
    log_event(AuditLog.Action.REVERSE, request=request, obj=mirror, extra={"reverses": entry.pk})
    return mirror


# ------------------------------------------------------------------------------------------ donations
@transaction.atomic
def confirm_donation(request: HttpRequest, donation: Any) -> LedgerEntry:
    """Mark a website pledge as received AND create the income entry (approved later by someone else)."""
    from giving.services import confirm_donation as giving_confirm

    if not giving_confirm(donation, request):
        raise ValidationError("This donation was already confirmed or cannot be confirmed.")
    entry = LedgerEntry.objects.create(
        kind=LedgerEntry.Kind.INCOME,
        date=donation.given_on or timezone.localdate(),
        amount=donation.amount,
        currency=donation.currency,
        income_source="donation",
        description=f"Donation {donation.receipt_number or donation.pk}",
        counterparty="" if donation.is_anonymous else donation.donor_name,
        reference=donation.receipt_number or "",
        donation=donation,
        recorded_by=request.user,
        status=E.SUBMITTED,
        submitted_at=timezone.now(),
    )
    log_event(AuditLog.Action.ADD, request=request, obj=entry, extra={"from_donation": donation.pk})
    return entry


# ------------------------------------------------------------------------------------------ donor pipeline
def donor_from_enquiry(enquiry: Any) -> Donor:
    """A website partnership registration becomes a 'prospect' in the donor/partner pipeline."""
    existing = Donor.objects.filter(source_enquiry=enquiry).first()
    if existing:
        return existing
    kind = enquiry.partner_type if enquiry.partner_type in Donor.Kind.values else Donor.Kind.INDIVIDUAL
    return Donor.objects.create(
        kind=kind,
        name=enquiry.organisation or enquiry.name,
        contact_person=enquiry.name if enquiry.organisation else "",
        email=enquiry.email,
        phone=enquiry.phone,
        country=enquiry.country,
        city=getattr(enquiry, "city", ""),
        interests=list(getattr(enquiry, "areas", []) or []),
        partnership_types=list(getattr(enquiry, "partnership_types", []) or []),
        source_enquiry=enquiry,
        next_step="Thank them and arrange a first conversation",
        next_step_due=timezone.localdate() + timedelta(days=7),
    )


# ------------------------------------------------------------------------------------------ volunteers
VOLUNTEER_STEPS = {
    "references": ((FinanceVolunteer.Status.SUBMITTED,), FinanceVolunteer.Status.REFERENCES),
    "interview": ((FinanceVolunteer.Status.REFERENCES,), FinanceVolunteer.Status.INTERVIEW),
    "approve": ((FinanceVolunteer.Status.INTERVIEW,), FinanceVolunteer.Status.APPROVED),
    "decline": (
        (
            FinanceVolunteer.Status.SUBMITTED,
            FinanceVolunteer.Status.REFERENCES,
            FinanceVolunteer.Status.INTERVIEW,
        ),
        FinanceVolunteer.Status.DECLINED,
    ),
}


@transaction.atomic
def volunteer_step(request: HttpRequest, volunteer: FinanceVolunteer, step: str) -> None:
    if step not in VOLUNTEER_STEPS:
        raise ValidationError("Unknown step.")
    sources, target = VOLUNTEER_STEPS[step]
    if volunteer.status not in sources:
        raise ValidationError("That step is not possible now.")
    if step in ("interview", "approve") and not volunteer.references_checked:
        raise ValidationError("Record that references were checked first (Edit).")
    volunteer.status = target
    if step in ("approve", "decline"):
        volunteer.decided_by = request.user
        volunteer.decided_at = timezone.now()
    volunteer.save()
    log_event(
        AuditLog.Action.APPROVE if step == "approve" else AuditLog.Action.CHANGE,
        request=request,
        obj=volunteer,
        extra={"step": step},
    )


# ------------------------------------------------------------------------------------------ reporting
def totals(entries: QuerySet) -> dict[str, Decimal]:
    posted = entries.filter(status=E.POSTED)
    income = posted.filter(kind=LedgerEntry.Kind.INCOME).aggregate(t=Sum("amount"))["t"] or ZERO
    expense = posted.filter(kind=LedgerEntry.Kind.EXPENSE).aggregate(t=Sum("amount"))["t"] or ZERO
    return {"income": income, "expense": expense, "net": income - expense}


def budget_vs_actual(year: int, department_code: str | None = None) -> list[dict[str, Any]]:
    """Per department (or per line for one department): budget, posted spend, remaining, percent used."""
    lines = BudgetLine.objects.filter(year=year).select_related("department")
    spend = LedgerEntry.objects.filter(status=E.POSTED, kind=LedgerEntry.Kind.EXPENSE, date__year=year)
    if department_code:
        lines = lines.filter(department__code=department_code)
        spend = spend.filter(department__code=department_code)
        by_line = dict(spend.values_list("budget_line_id").annotate(t=Sum("amount")))
        rows = [
            {
                "label": line.name,
                "category": line.get_category_display(),
                "budget": line.amount,
                "actual": by_line.get(line.pk) or ZERO,
            }
            for line in lines
        ]
        unbudgeted = by_line.get(None)
        if unbudgeted:
            rows.append(
                {"label": "Not linked to a budget line", "category": "", "budget": ZERO, "actual": unbudgeted}
            )
    else:
        budget: dict[str, Decimal] = defaultdict(lambda: ZERO)
        names: dict[str, str] = {}
        for line in lines:
            budget[line.department.code] += line.amount
            names[line.department.code] = line.department.name
        actual = {}
        for code, name, total in spend.values_list("department__code", "department__name").annotate(
            t=Sum("amount")
        ):
            actual[code] = total
            names.setdefault(code, name or "No department")
        rows = [
            {
                "label": names[c],
                "category": "",
                "budget": budget.get(c, ZERO),
                "actual": actual.get(c) or ZERO,
            }
            for c in names
        ]
    for row in rows:
        row["remaining"] = row["budget"] - row["actual"]
        row["percent"] = int(row["actual"] * 100 / row["budget"]) if row["budget"] else None
    return rows


def burn_rate(today: date | None = None, months: int = 3) -> Decimal:
    """Average posted monthly expenditure over the last ``months`` full months."""
    today = today or timezone.localdate()
    end = today.replace(day=1)
    start_month = end.month - months
    start_year = end.year
    while start_month <= 0:
        start_month += 12
        start_year -= 1
    start = date(start_year, start_month, 1)
    spent = (
        LedgerEntry.objects.filter(
            status=E.POSTED, kind=LedgerEntry.Kind.EXPENSE, date__gte=start, date__lt=end
        ).aggregate(t=Sum("amount"))["t"]
        or ZERO
    )
    return (spent / months).quantize(Decimal("0.01"))
