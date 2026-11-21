"""Discipleship services: the Missions handoff, follow-up steps, enrolment and the minors rule."""

from __future__ import annotations

from typing import Any

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import Cohort, Disciple, Enrollment, FollowUp, Registration, default_follow_up_due

F = FollowUp.Status

FOLLOW_UP_STEPS: dict[str, tuple[tuple[str, ...], str]] = {
    "contacted": ((F.NEW,), F.CONTACTED),
    "first_visit": ((F.NEW, F.CONTACTED), F.FIRST_VISIT),
    "enroll": ((F.CONTACTED, F.FIRST_VISIT), F.ENROLLED),
    "milestone": ((F.ENROLLED,), F.MILESTONE),
    "completed": ((F.ENROLLED, F.MILESTONE), F.COMPLETED),
    "lost": ((F.NEW, F.CONTACTED, F.FIRST_VISIT), F.LOST),
}
STEP_LABELS = {
    "contacted": "Mark contacted",
    "first_visit": "First visit done",
    "enroll": "Enrol in discipleship",
    "milestone": "Milestone review",
    "completed": "Follow-up completed",
    "lost": "Could not be reached",
}


def hand_off(convert: Any) -> FollowUp:
    """Called when Missions records a new convert: create the Discipleship follow-up task."""
    follow, created = FollowUp.objects.get_or_create(
        convert=convert,
        defaults={
            "due_date": default_follow_up_due(convert.decision_date),
            "branch_id": convert.branch_id,
            "is_minor": convert.is_minor,
        },
    )
    if created:
        log_event(
            AuditLog.Action.HANDOFF,
            obj=follow,
            actor_email="system:missions-to-discipleship",
            extra={"from": "missions", "to": "discipleship", "convert": convert.pk},
        )
    return follow


def _disciple_from_convert(convert: Any) -> Disciple:
    disciple = getattr(convert, "disciple", None)
    if disciple is not None:
        return disciple
    return Disciple.objects.create(
        full_name=convert.full_name,
        phone=convert.phone,
        gender=convert.gender,
        age_band=convert.age_band,
        branch_id=convert.branch_id,
        source=Disciple.Source.CONVERT,
        convert=convert,
    )


@transaction.atomic
def follow_up_step(
    request: HttpRequest, follow: FollowUp, step: str, cohort: Cohort | None = None
) -> FollowUp:
    if step not in FOLLOW_UP_STEPS:
        raise ValidationError("Unknown step.")
    sources, target = FOLLOW_UP_STEPS[step]
    if follow.status not in sources:
        raise ValidationError(f"Not possible while the follow-up is '{follow.get_status_display()}'.")
    if step == "enroll":
        disciple = _disciple_from_convert(follow.convert)
        follow.disciple = disciple
        if cohort is not None:
            Enrollment.objects.get_or_create(cohort=cohort, disciple=disciple)
            disciple.stage = Disciple.Stage.IN_CLASS
            disciple.save(update_fields=["stage", "updated_at"])
    if step in ("contacted", "first_visit"):
        follow.last_contact = timezone.localdate()
    follow.status = target
    follow.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=follow, extra={"step": step})
    return follow


@transaction.atomic
def enroll_registration(
    request: HttpRequest, registration: Registration, cohort: Cohort | None = None
) -> Disciple:
    if registration.status == Registration.Status.DECLINED:
        raise ValidationError("This registration was not taken forward.")
    if registration.is_minor and not (registration.guardian_consent and registration.guardian_contact):
        raise ValidationError("Under 18: record the guardian's contact and consent before enrolling.")
    disciple = getattr(registration, "disciple", None) or Disciple.objects.create(
        full_name=registration.full_name,
        phone=registration.phone,
        email=registration.email,
        gender=registration.gender,
        age_band=registration.age_band,
        branch=registration.branch,
        source=Disciple.Source.REGISTRATION,
        registration=registration,
        growth_areas=registration.growth_areas,
    )
    if cohort is not None:
        Enrollment.objects.get_or_create(cohort=cohort, disciple=disciple)
        disciple.stage = Disciple.Stage.IN_CLASS
        disciple.save(update_fields=["stage", "updated_at"])
    registration.status = Registration.Status.ENROLLED
    registration.save()
    # Decision 8: the disciple record now holds the person; the registration keeps only a reference.
    from core.retention import convert

    convert(registration, f"Disciple #{disciple.pk}")
    log_event(AuditLog.Action.APPROVE, request=request, obj=registration, extra={"disciple": disciple.pk})
    return disciple


def set_registration_status(request: HttpRequest, registration: Registration, status: str) -> None:
    if status not in (Registration.Status.CONTACTED, Registration.Status.DECLINED):
        raise ValidationError("Unknown step.")
    if registration.status in (Registration.Status.ENROLLED, Registration.Status.DECLINED):
        raise ValidationError("This registration is already closed.")
    registration.status = status
    registration.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=registration, extra={"status": status})
