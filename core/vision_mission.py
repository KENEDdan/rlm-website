"""Vision and Mission changes: draft -> preview -> approval (Super Admin / Executive Director) -> publish.

* Anyone in the Technical Team (or the Super Admin) drafts a change and previews it on the real page layout.
* While ``SiteSettings.vision_mission_approval_required`` is on (the default), a draft must be submitted and
  approved by an active Super Admin or the Executive Director (``finance.Approver`` row) who did not write it;
  the approval needs password + 2FA again. Only then can it be published.
* Publishing writes the text to ``SiteContent`` (the single source used by every page) and keeps the old text on
  the change row, so the published rows are the version history. Rolling back proposes an earlier published text
  again: an approver's rollback is approved and published in one click; anyone else's waits for approval.
* Every step is audit-logged.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from accounts import reauth
from audit.models import AuditLog
from audit.services import log_event

from .models import ContentChangeRequest, SiteContent, SiteSettings

S = ContentChangeRequest.Status


class ChangeError(Exception):
    """A rule was broken; the message is safe to show."""


def approval_required() -> bool:
    return SiteSettings.load().vision_mission_approval_required


def is_approver(user: Any) -> bool:
    """Active Super Admin, or a current Founder / Executive Director approver."""
    if not getattr(user, "is_authenticated", False):
        return False
    if getattr(user, "is_super_admin", False):
        return True
    from finance.models import Approver

    today = timezone.localdate()
    for row in Approver.objects.filter(user=user, is_active=True, role__in=["founder", "executive_director"]):
        if (row.starts_on is None or row.starts_on <= today) and (
            row.ends_on is None or today <= row.ends_on
        ):
            return True
    return False


def can_draft(user: Any) -> bool:
    return bool(getattr(user, "is_authenticated", False)) and (
        getattr(user, "is_super_admin", False) or user.has_perm("core.add_contentchangerequest")
    )


def history(field: str) -> QuerySet:
    return ContentChangeRequest.objects.filter(field=field, status=S.PUBLISHED).order_by(
        "-published_at", "-pk"
    )


def open_changes() -> QuerySet:
    return ContentChangeRequest.objects.filter(status__in=[S.DRAFT, S.SUBMITTED, S.APPROVED]).select_related(
        "created_by"
    )


def _log(request: HttpRequest, change: ContentChangeRequest, step: str) -> None:
    log_event(
        AuditLog.Action.CHANGE,
        request=request,
        obj=change,
        extra={"step": step, "field": change.field},
    )


def create_draft(request: HttpRequest, field: str, text: str, reason: str = "") -> ContentChangeRequest:
    if not can_draft(request.user):
        raise ChangeError("You may not draft changes to the Vision or Mission.")
    if field not in ContentChangeRequest.Field.values:
        raise ChangeError("Unknown field.")
    text = text.strip()
    if not text:
        raise ChangeError("Write the new text first.")
    if text == getattr(SiteContent.load(), field):
        raise ChangeError("This is the text that is already published.")
    change = ContentChangeRequest.objects.create(
        field=field,
        text=text,
        reason=reason.strip()[:300],
        created_by=request.user,
        status=S.DRAFT,
    )
    _log(request, change, "draft")
    return change


def update_draft(request: HttpRequest, change: ContentChangeRequest, text: str, reason: str) -> None:
    if change.status != S.DRAFT or change.created_by_id != request.user.pk:
        raise ChangeError("Only the author can edit a draft, and only before it is submitted.")
    change.text, change.reason = text.strip(), reason.strip()[:300]
    change.save(update_fields=["text", "reason", "updated_at"])
    _log(request, change, "edit")


def submit(request: HttpRequest, change: ContentChangeRequest) -> None:
    if change.status != S.DRAFT or change.created_by_id != request.user.pk:
        raise ChangeError("Only the author can submit their own draft.")
    change.status, change.submitted_at = S.SUBMITTED, timezone.now()
    change.save(update_fields=["status", "submitted_at", "updated_at"])
    _log(request, change, "submit")


def _decide(request: HttpRequest, change: ContentChangeRequest, approve: bool, note: str) -> None:
    if not is_approver(request.user):
        raise ChangeError(
            "Only the Super Admin or the Executive Director can approve Vision and Mission changes."
        )
    if change.created_by_id == request.user.pk:
        raise ChangeError("You cannot approve your own change. Another approver must decide.")
    if change.status != S.SUBMITTED:
        raise ChangeError("Only submitted changes can be decided.")
    if not reauth.is_fresh(request):
        raise reauth.ReauthRequired
    if not approve and not note.strip():
        raise ChangeError("Give a short reason when a change is not approved.")
    change.status = S.APPROVED if approve else S.REJECTED
    change.decided_by, change.decided_at, change.decision_note = (
        request.user,
        timezone.now(),
        note.strip()[:300],
    )
    change.save(
        update_fields=[
            "status",
            "decided_by",
            "decided_at",
            "decision_note",
            "updated_at",
        ]
    )
    _log(request, change, "approve" if approve else "reject")


def approve(request: HttpRequest, change: ContentChangeRequest, note: str = "") -> None:
    _decide(request, change, True, note)


def reject(request: HttpRequest, change: ContentChangeRequest, note: str) -> None:
    _decide(request, change, False, note)


def withdraw(request: HttpRequest, change: ContentChangeRequest) -> None:
    if change.created_by_id != request.user.pk and not getattr(request.user, "is_super_admin", False):
        raise ChangeError("Only the author or the Super Admin can withdraw a change.")
    if change.status not in (S.DRAFT, S.SUBMITTED, S.APPROVED):
        raise ChangeError("This change is already closed.")
    change.status = S.WITHDRAWN
    change.save(update_fields=["status", "updated_at"])
    _log(request, change, "withdraw")


@transaction.atomic
def publish(request: HttpRequest, change: ContentChangeRequest) -> None:
    required = approval_required()
    user = request.user
    if required and change.status != S.APPROVED:
        raise ChangeError("This change must be approved before it can be published.")
    if not required and change.status not in (S.DRAFT, S.SUBMITTED, S.APPROVED):
        raise ChangeError("This change is closed.")
    if not (change.created_by_id == user.pk or is_approver(user)):
        raise ChangeError("Only the author or an approver can publish.")
    content = SiteContent.objects.select_for_update().get(pk=SiteContent.load().pk)
    change.previous_text = getattr(content, change.field)
    setattr(content, change.field, change.text)
    content.vision_mission_updated_at = timezone.now()
    content.save()
    change.status, change.published_by, change.published_at = (
        S.PUBLISHED,
        user,
        timezone.now(),
    )
    change.approval_was_required = required
    change.save(
        update_fields=[
            "status",
            "previous_text",
            "published_by",
            "published_at",
            "approval_was_required",
            "updated_at",
        ]
    )
    # Anything else still open for the same field was written against the old text.
    ContentChangeRequest.objects.filter(
        field=change.field, status__in=[S.DRAFT, S.SUBMITTED, S.APPROVED]
    ).exclude(pk=change.pk).update(status=S.SUPERSEDED, updated_at=timezone.now())
    _log(request, change, "publish")


def rollback(request: HttpRequest, version: ContentChangeRequest) -> ContentChangeRequest:
    """Propose an earlier published text again; approvers get it approved and published in one click."""
    if version.status != S.PUBLISHED:
        raise ChangeError("Only a published version can be restored.")
    current = getattr(SiteContent.load(), version.field)
    if version.text == current:
        raise ChangeError("This version is the one already published.")
    if not can_draft(request.user):
        raise ChangeError("You may not change the Vision or Mission.")
    change = ContentChangeRequest.objects.create(
        field=version.field,
        text=version.text,
        reason=f"Rollback to the version published {version.published_at:%d %b %Y}",
        created_by=request.user,
        rollback_of=version,
        status=S.DRAFT,
    )
    _log(request, change, "rollback")
    if not approval_required():
        publish(request, change)
    elif is_approver(request.user):
        if not reauth.is_fresh(request):
            raise reauth.ReauthRequired
        # The approver's own one-click rollback: they restore text that was already approved once.
        change.status, change.submitted_at = S.APPROVED, timezone.now()
        change.decided_by, change.decided_at = request.user, timezone.now()
        change.decision_note = "Rollback by approver"
        change.save()
        publish(request, change)
    else:
        submit(request, change)
    return change
