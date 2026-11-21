"""Protected change of bank and payment details (fraud prevention, D-034).

1. The Finance & Resource Mobilization head (or the Super Admin) proposes new details after re-authenticating
   (password + 2FA). The change is saved as PENDING; the live details do not change.
2. An email alert goes to the Finance heads and the Super Admins/Founder: who asked, when, and the masked new
   account number ("****1234"), never the full number.
3. A SECOND authorised person - the Founder or Executive Director (Super Admin or ``finance.Approver`` row), never
   the person who proposed it - confirms after re-authenticating. Only then are the live details replaced and the
   "Last verified" date updated. Rejections and cancellations are kept too.
4. Every step is in the audit log, and every change row (with the details it replaced, encrypted) is kept.

Nobody else can read these screens: not the Technical Team, not other Finance members, not any other role.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import Q
from django.http import HttpRequest
from django.utils import timezone

from accounts import reauth
from audit.models import AuditLog
from audit.services import log_event

from .models import BANK_FIELDS, BankDetailChange, GivingSettings

C = BankDetailChange.Status


class BankChangeError(Exception):
    """A rule was broken; the message is safe to show."""


def _finance_head(user: Any) -> bool:
    from portal.models import DepartmentMembership

    return DepartmentMembership.objects.filter(user=user, department__code="finance", is_head=True).exists()


def can_propose(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False)) and (
        getattr(user, "is_super_admin", False) or _finance_head(user)
    )


def can_confirm(user: Any) -> bool:
    from core.vision_mission import is_approver  # Super Admin, Founder or Executive Director

    return is_approver(user)


def can_view(user: Any) -> bool:
    return can_propose(user) or can_confirm(user)


def pending() -> BankDetailChange | None:
    return BankDetailChange.objects.filter(status=C.PENDING).select_related("requested_by").first()


def _current_values(gs: GivingSettings) -> dict[str, Any]:
    return {f: getattr(gs, f) for f in BANK_FIELDS}


def _alert_recipients() -> list[str]:
    from accounts.models import User
    from portal.models import DepartmentMembership

    heads = DepartmentMembership.objects.filter(department__code="finance", is_head=True).values_list(
        "user_id", flat=True
    )
    users = User.objects.filter(
        Q(is_superuser=True) | Q(pk__in=heads), is_active=True, deleted_at__isnull=True
    )
    return sorted({email for email in users.values_list("email", flat=True) if email})


def _alert(change: BankDetailChange, event: str) -> None:
    """Email WITHOUT the account number (only its last four characters)."""
    from core.models import SiteContent

    site = SiteContent.load()
    lines = [
        f"Bank details change #{change.pk}: {event}.",
        "",
        f"Requested by: {change.requested_by.full_name if change.requested_by else 'unknown'}",
        f"Requested at: {timezone.localtime(change.created_at):%d %b %Y %H:%M}",
        f"New account number ends in: {change.masked_account_number or '(none)'}",
        f"Bank: {change.bank_name or '(none)'}",
    ]
    if change.decided_by:
        lines.append(
            f"Decided by: {change.decided_by.full_name} at {timezone.localtime(change.decided_at):%d %b %Y %H:%M}"
        )
    lines += [
        "",
        "If you did not expect this change, contact the Super Admin immediately and do not confirm it.",
        "The full details are visible only in the staff portal (Finance > Bank details).",
    ]
    recipients = _alert_recipients()
    if recipients:
        send_mail(
            subject=f"[{site.short_name}] Bank details change {event}",
            message="\n".join(lines),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )


def _require_fresh(request: HttpRequest) -> None:
    if not reauth.is_fresh(request):
        raise reauth.ReauthRequired


@transaction.atomic
def propose(request: HttpRequest, data: dict[str, Any], reason: str) -> BankDetailChange:
    user = request.user
    if not can_propose(user):
        raise BankChangeError(
            "Only the Finance & Resource Mobilization head or the Super Admin can propose changes."
        )
    _require_fresh(request)
    if not reason.strip():
        raise BankChangeError("Say why the details change (e.g. new account opened).")
    if BankDetailChange.objects.select_for_update().filter(status=C.PENDING).exists():
        raise BankChangeError(
            "Another change is already waiting for confirmation. Confirm or cancel it first."
        )
    current = _current_values(GivingSettings.load())
    if all(current[f] == data.get(f, current[f]) for f in BANK_FIELDS):
        raise BankChangeError("Nothing has changed.")
    change = BankDetailChange.objects.create(
        **{f: data.get(f, current[f]) for f in BANK_FIELDS},
        reason=reason.strip()[:300],
        requested_by=user,
        status=C.PENDING,
    )
    log_event(AuditLog.Action.CHANGE, request=request, obj=change, extra={"step": "proposed"})
    _alert(change, "requested (waiting for confirmation)")
    return change


@transaction.atomic
def confirm(request: HttpRequest, change: BankDetailChange) -> None:
    user = request.user
    if not can_confirm(user):
        raise BankChangeError("Only the Founder or the Executive Director can confirm bank detail changes.")
    if change.requested_by_id == user.pk:
        raise BankChangeError("A second person must confirm: you proposed this change.")
    _require_fresh(request)
    change = BankDetailChange.objects.select_for_update().get(pk=change.pk)
    if change.status != C.PENDING:
        raise BankChangeError("This change is no longer waiting for confirmation.")
    gs = GivingSettings.load()
    change.previous = json.dumps(_current_values(gs))
    for field in BANK_FIELDS:
        setattr(gs, field, getattr(change, field))
    now = timezone.now()
    gs.bank_details_verified_at, gs.bank_details_verified_by = now, user
    gs._bank_change_confirmed = True  # type: ignore[attr-defined]
    gs.save()
    change.status, change.decided_by, change.decided_at = C.CONFIRMED, user, now
    change.save(update_fields=["status", "previous", "decided_by", "decided_at", "updated_at"])
    log_event(AuditLog.Action.CHANGE, request=request, obj=change, extra={"step": "confirmed"})
    _alert(change, "CONFIRMED and now live")


@transaction.atomic
def reject(request: HttpRequest, change: BankDetailChange, note: str) -> None:
    if not can_confirm(request.user):
        raise BankChangeError("Only the Founder or the Executive Director can reject bank detail changes.")
    _require_fresh(request)
    if change.status != C.PENDING:
        raise BankChangeError("This change is no longer waiting for confirmation.")
    if not note.strip():
        raise BankChangeError("Give a short reason.")
    change.status, change.decided_by, change.decided_at = C.REJECTED, request.user, timezone.now()
    change.decision_note = note.strip()[:300]
    change.save(update_fields=["status", "decided_by", "decided_at", "decision_note", "updated_at"])
    log_event(AuditLog.Action.CHANGE, request=request, obj=change, extra={"step": "rejected"})
    _alert(change, "rejected")


@transaction.atomic
def cancel(request: HttpRequest, change: BankDetailChange) -> None:
    if change.requested_by_id != request.user.pk and not getattr(request.user, "is_super_admin", False):
        raise BankChangeError("Only the person who proposed the change or the Super Admin can cancel it.")
    if change.status != C.PENDING:
        raise BankChangeError("This change is no longer waiting for confirmation.")
    change.status, change.decided_by, change.decided_at = C.CANCELLED, request.user, timezone.now()
    change.save(update_fields=["status", "decided_by", "decided_at", "updated_at"])
    log_event(AuditLog.Action.CHANGE, request=request, obj=change, extra={"step": "cancelled"})
    _alert(change, "cancelled")
