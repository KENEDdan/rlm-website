"""Membership workflow and communications.

Admission: received -> under review -> approved / not accepted -> orientation -> integration -> active.
Approve/reject are head-only decisions and email the applicant (nothing they wrote is repeated in the email).
Minors (under 18) cannot be approved until a guardian's details and consent are recorded.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.mail import send_mail
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event
from core.models import SiteContent

from .models import Activity, Attendance, BulkMessage, Member

S = Member.Status

# transition -> (allowed from, new status, needs head)
TRANSITIONS: dict[str, tuple[tuple[str, ...], str, bool]] = {
    "review": ((S.SUBMITTED,), S.UNDER_REVIEW, False),
    "approve": ((S.SUBMITTED, S.UNDER_REVIEW), S.APPROVED, True),
    "reject": ((S.SUBMITTED, S.UNDER_REVIEW), S.REJECTED, True),
    "orientation": ((S.APPROVED,), S.ORIENTATION, False),
    "integration": ((S.APPROVED, S.ORIENTATION), S.INTEGRATION, False),
    "activate": ((S.APPROVED, S.ORIENTATION, S.INTEGRATION, S.INACTIVE), S.ACTIVE, False),
    "deactivate": ((S.ACTIVE, S.INTEGRATION, S.ORIENTATION, S.APPROVED), S.INACTIVE, True),
    "transfer": ((S.ACTIVE, S.INACTIVE, S.INTEGRATION), S.TRANSFERRED, True),
}
LABELS = {
    "review": "Start review",
    "approve": "Approve",
    "reject": "Do not accept",
    "orientation": "Start orientation",
    "integration": "Start integration",
    "activate": "Mark active",
    "deactivate": "Mark inactive",
    "transfer": "Mark transferred",
}


def available_transitions(member: Member, *, is_head: bool) -> list[str]:
    return [
        name
        for name, (sources, _, head_only) in TRANSITIONS.items()
        if member.status in sources and (is_head or not head_only)
    ]


@transaction.atomic
def transition(request: HttpRequest, member: Member, name: str, *, is_head: bool, note: str = "") -> Member:
    if name not in TRANSITIONS:
        raise ValidationError("Unknown step.")
    sources, target, head_only = TRANSITIONS[name]
    if head_only and not is_head:
        raise PermissionDenied
    if member.status not in sources:
        raise ValidationError(
            f"This step is not possible while the record is '{member.get_status_display()}'."
        )
    if name == "approve" and member.is_minor and not (member.guardian_consent and member.guardian_contact):
        raise ValidationError("This applicant is under 18: record the guardian's details and consent first.")
    if name == "reject" and not note.strip():
        raise ValidationError("Please give a short reason (kept private, not sent to the applicant).")
    if name == "transfer" and not member.transferred_to:
        raise ValidationError("Fill in 'Transferred to' first (Edit).")
    member.status = target
    if name in ("approve", "reject"):
        member.decided_by = request.user
        member.decided_at = timezone.now()
        member.decision_note = note.strip()[:2000]
    if name == "approve" and not member.join_date:
        member.join_date = timezone.localdate()
    member.save()
    action = {"approve": AuditLog.Action.APPROVE, "reject": AuditLog.Action.REJECT}.get(
        name, AuditLog.Action.CHANGE
    )
    log_event(action, request=request, obj=member, extra={"step": name, "status": target})
    if name in ("approve", "reject") and member.email:
        pk = member.pk
        transaction.on_commit(lambda: send_decision_email(pk))
    return member


def send_decision_email(member_pk: int) -> bool:
    member = Member.objects.filter(pk=member_pk).first()
    if member is None or not member.email or member.status not in (S.APPROVED, S.REJECTED):
        return False
    site = SiteContent.load()
    context = {"member": member, "site": site, "approved": member.status == S.APPROVED}
    send_mail(
        subject=render_to_string("emails/member_decision_subject.txt", context).strip(),
        message=render_to_string("emails/member_decision.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[member.email],
    )
    return True


# ------------------------------------------------------------------------------------------ participation
ENGAGEMENT_WINDOW_DAYS = 90


def recompute_engagement(member: Member) -> int:
    """0-100: share of the branch's activities in the last 90 days the member attended, +10 if serving."""
    since = timezone.localdate() - timedelta(days=ENGAGEMENT_WINDOW_DAYS)
    activities = Activity.objects.filter(date__gte=since)
    if member.branch_id:
        activities = activities.filter(branch_id__in=[member.branch_id, None])
    total = activities.count()
    attended = Attendance.objects.filter(member=member, present=True, activity__in=activities).count()
    score = int(attended * 100 / total) if total else 0
    if any(r.is_current for r in member.service_records.all()):
        score += 10
    score = min(score, 100)
    Member.objects.filter(pk=member.pk).update(engagement_score=score)
    return score


@transaction.atomic
def record_attendance(
    request: HttpRequest, activity: Activity, present_ids: set[int], members: QuerySet
) -> int:
    """Save present/absent for every member shown on the attendance sheet (members = scoped queryset)."""
    count = 0
    for member in members:
        Attendance.objects.update_or_create(
            activity=activity, member=member, defaults={"present": member.pk in present_ids}
        )
        count += 1
    for member in members:
        recompute_engagement(member)
    log_event(AuditLog.Action.CHANGE, request=request, obj=activity, extra={"attendance_rows": count})
    return count


# ------------------------------------------------------------------------------------------ bulk messages
def recipients(message: BulkMessage, scoped_members: QuerySet) -> QuerySet:
    """Only people who opted in; never minors; only current members of the chosen branch."""
    statuses = (S.ACTIVE,) if message.audience == BulkMessage.Audience.ACTIVE else Member.CURRENT
    qs = scoped_members.filter(comms_opt_in=True, is_minor=False, status__in=statuses)
    if message.branch_id:
        qs = qs.filter(branch_id=message.branch_id)
    return qs


@transaction.atomic
def send_bulk_email(request: HttpRequest, message: BulkMessage, scoped_members: QuerySet) -> int:
    if message.sent_at:
        raise ValidationError("This message was already sent.")
    if message.channel != BulkMessage.Channel.EMAIL:
        raise ValidationError("This message is set up for WhatsApp links.")
    people = [m for m in recipients(message, scoped_members) if m.email]
    message.sent_at = timezone.now()
    message.recipient_count = len(people)
    message.save(update_fields=["sent_at", "recipient_count", "updated_at"])
    log_event(AuditLog.Action.CHANGE, request=request, obj=message, extra={"sent_to": len(people)})
    ids = [m.pk for m in people]
    from .tasks import send_bulk_message

    transaction.on_commit(lambda: send_bulk_message.delay(message.pk, ids))
    return len(people)


def whatsapp_links(message: BulkMessage, scoped_members: QuerySet) -> list[dict[str, Any]]:
    text = quote(f"{message.subject}\n\n{message.body}")
    links = []
    for member in recipients(message, scoped_members):
        digits = "".join(ch for ch in member.phone if ch.isdigit())
        if len(digits) >= 8:
            links.append({"member": member, "url": f"https://wa.me/{digits}?text={text}"})
    return links
