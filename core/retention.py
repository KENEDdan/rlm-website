"""Application retention (ministry decision 8).

Four application types: membership, discipleship, partnership and finance-volunteer. Each has an outcome
(pending / successful / unsuccessful) and an ``outcome_at`` date.

* Successful: converted into the proper record. Membership and finance-volunteer applications become the member
  register / vetted volunteer list entry themselves (no second copy of anyone's data is made). Discipleship
  registrations become a Disciple (and cohort enrolment) and partnership registrations a partner-pipeline entry;
  their application rows are then emptied of personal data and keep only ``record_reference``.
* Unsuccessful: deleted ``retention_unsuccessful_days`` after the decision (minors: the shorter
  ``retention_unsuccessful_minor_days``) by the daily ``purge_unsuccessful_applications`` job, unless on legal
  hold. Only an anonymous count (type, branch, month, outcome) survives in ``ApplicationStat``. Uploaded files of
  the deleted rows are removed from storage too. Every run is written to the audit log, also when nothing was due.
"""

from __future__ import annotations

import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

from django.apps import apps
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import models, router, transaction
from django.db.models import F
from django.db.models.deletion import Collector, ProtectedError
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import ApplicationStat, RetainedApplication, SiteSettings

logger = logging.getLogger(__name__)
OUTCOME = RetainedApplication.Outcome


@dataclass(frozen=True)
class Spec:
    code: str
    label: str
    model_label: str
    department: str
    pending: tuple[str, ...] = ()
    unsuccessful: tuple[str, ...] = ()
    successful: tuple[str, ...] = ()
    strip_on_success: tuple[str, ...] = ()  # personal fields emptied once converted
    resource_slug: str = ""

    @property
    def model(self) -> type[models.Model]:
        return apps.get_model(self.model_label)

    def outcome_for(self, status: str) -> str | None:
        if status in self.unsuccessful:
            return OUTCOME.UNSUCCESSFUL
        if status in self.successful:
            return OUTCOME.SUCCESSFUL
        if status in self.pending:
            return OUTCOME.PENDING
        return None


SPECS: dict[str, Spec] = {
    "membership": Spec(
        "membership",
        "Membership application",
        "membership.Member",
        "membership",
        pending=("submitted", "under_review"),
        unsuccessful=("rejected",),
        successful=("approved", "orientation", "integration", "active", "inactive"),
        resource_slug="members",
    ),
    "discipleship": Spec(
        "discipleship",
        "Discipleship registration",
        "discipleship.Registration",
        "discipleship",
        pending=("submitted", "contacted"),
        unsuccessful=("declined",),
        successful=("enrolled",),
        strip_on_success=(
            "full_name",
            "age",
            "phone",
            "email",
            "email_hash",
            "born_again",
            "baptized",
            "attends_church",
            "journey",
            "guardian_name",
            "guardian_contact",
            "nationality",
            "city",
            "gender",
        ),
        resource_slug="registrations",
    ),
    "partnership": Spec(
        "partnership",
        "Partnership registration",
        "giving.PartnershipEnquiry",
        "finance",
        strip_on_success=(
            "name",
            "organisation",
            "email",
            "email_hash",
            "phone",
            "city",
            "message",
            "internal_notes",
            "other_area",
        ),
        resource_slug="partner-registrations",
    ),
    "finance_volunteer": Spec(
        "finance_volunteer",
        "Finance volunteer application",
        "finance.FinanceVolunteer",
        "finance",
        pending=("submitted", "references", "interview"),
        unsuccessful=("declined",),
        successful=("approved",),
        resource_slug="volunteers",
    ),
}
REFERENCE = {"membership": "Member register", "finance_volunteer": "Vetted finance-volunteer list"}


def spec_for(obj: models.Model) -> Spec | None:
    label = obj._meta.label
    return next((s for s in SPECS.values() if s.model_label == label), None)


# ------------------------------------------------------------------------------------------------ outcome
def sync_outcome(obj: Any) -> None:
    """Called before save: keep ``outcome`` in step with the status and start the retention clock."""
    spec = spec_for(obj)
    if spec is None or not spec.pending:
        return
    outcome = spec.outcome_for(getattr(obj, "status", ""))
    if outcome is None or outcome == obj.outcome:
        return
    obj.outcome = outcome
    obj.outcome_at = None if outcome == OUTCOME.PENDING else timezone.now()
    if outcome == OUTCOME.SUCCESSFUL and spec.code in REFERENCE and not obj.record_reference:
        obj.record_reference = REFERENCE[spec.code]
        obj._count_success = True  # counted after save (needs the pk-independent month/branch only)


def count(spec: Spec, obj: Any, outcome: str) -> None:
    created = getattr(obj, "created_at", None) or timezone.now()
    month = timezone.localtime(created).date().replace(day=1)
    stat, _ = ApplicationStat.objects.get_or_create(
        kind=spec.code, branch_id=getattr(obj, "branch_id", None), month=month, outcome=outcome
    )
    ApplicationStat.objects.filter(pk=stat.pk).update(count=F("count") + 1)


@transaction.atomic
def convert(obj: Any, reference: str) -> None:
    """Successful application converted into its proper record: empty the personal fields, keep a reference."""
    spec = spec_for(obj)
    if spec is None:
        return
    first_time = obj.outcome != OUTCOME.SUCCESSFUL or not obj.record_reference
    for name in spec.strip_on_success:
        field = obj._meta.get_field(name)
        setattr(obj, name, "" if not field.null else None)
    obj.outcome = OUTCOME.SUCCESSFUL
    obj.outcome_at = obj.outcome_at or timezone.now()
    obj.record_reference = reference[:80]
    obj.save()
    if first_time:
        count(spec, obj, OUTCOME.SUCCESSFUL)


def set_outcome(request: HttpRequest, obj: Any, outcome: str) -> None:
    """Explicit outcome for applications without a status workflow (partnership registrations)."""
    if outcome not in OUTCOME.values:
        raise ValidationError("Unknown outcome.")
    obj.outcome = outcome
    obj.outcome_at = None if outcome == OUTCOME.PENDING else timezone.now()
    obj.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=obj, extra={"outcome": outcome})


# ------------------------------------------------------------------------------------------------ deadlines
def deadline(obj: Any, site: SiteSettings | None = None) -> dt.datetime | None:
    """When an unsuccessful application will be deleted (None: not scheduled)."""
    if obj.outcome != OUTCOME.UNSUCCESSFUL or not obj.outcome_at:
        return None
    site = site or SiteSettings.load()
    days = site.retention_unsuccessful_days
    if not days:
        return None
    if getattr(obj, "is_minor", False) and site.retention_unsuccessful_minor_days:
        days = min(days, site.retention_unsuccessful_minor_days)
    return obj.outcome_at + dt.timedelta(days=days)


def deadline_text(obj: Any) -> str:
    if getattr(obj, "legal_hold", False):
        return f"On legal hold: not deleted ({obj.legal_hold_reason})"
    when = deadline(obj)
    if when is None:
        return (
            "Not scheduled (only unsuccessful applications are deleted)"
            if obj.outcome != OUTCOME.UNSUCCESSFUL
            else ("Kept: automatic deletion is switched off")
        )
    return f"Deleted automatically on {timezone.localtime(when):%d %b %Y}"


@dataclass
class Candidate:
    spec: Spec
    obj: Any
    deadline: dt.datetime | None

    @property
    def reference(self) -> str:
        return f"{self.spec.label} #{self.obj.pk}"

    @property
    def is_minor(self) -> bool:
        return bool(getattr(self.obj, "is_minor", False))


def unsuccessful(include_held: bool = False) -> list[Candidate]:
    site = SiteSettings.load()
    out = []
    for spec in SPECS.values():
        qs = spec.model.objects.filter(outcome=OUTCOME.UNSUCCESSFUL, outcome_at__isnull=False)
        if not include_held:
            qs = qs.filter(legal_hold=False)
        for obj in qs:
            out.append(Candidate(spec, obj, deadline(obj, site)))
    return out


def due(now: dt.datetime | None = None) -> list[Candidate]:
    now = now or timezone.now()
    return [c for c in unsuccessful() if c.deadline is not None and c.deadline <= now]


def nearing(days: int | None = None, now: dt.datetime | None = None) -> list[Candidate]:
    now = now or timezone.now()
    days = SiteSettings.load().retention_notice_days if days is None else days
    horizon = now + dt.timedelta(days=days)
    return sorted(
        (c for c in unsuccessful() if c.deadline is not None and now < c.deadline <= horizon),
        key=lambda c: c.deadline,  # type: ignore[arg-type, return-value]
    )


def held() -> list[Candidate]:
    out = []
    for spec in SPECS.values():
        for obj in spec.model.objects.filter(legal_hold=True):
            out.append(Candidate(spec, obj, deadline(obj)))
    return out


# ------------------------------------------------------------------------------------------------ erase
def _erase(spec: Spec, obj: Any) -> None:
    """Delete the application and everything that hangs off it, including stored files; count it first."""
    count(spec, obj, obj.outcome)
    if spec.code == "partnership":
        donor = getattr(obj, "donor", None)  # partner-pipeline prospect created from this registration
        if donor is not None:
            if donor.pledges.exists():
                donor.source_enquiry = None
                donor.save(update_fields=["source_enquiry", "updated_at"])
            else:
                _delete_with_files(donor)
    _delete_with_files(obj)


def _delete_with_files(obj: models.Model) -> None:
    collector = Collector(using=router.db_for_write(obj.__class__))
    collector.collect([obj])
    files = []
    # rows Django deletes one by one, and related rows it deletes in bulk ("fast deletes")
    groups: list[tuple[type[models.Model], Any]] = list(collector.data.items())
    groups += [(qs.model, qs) for qs in collector.fast_deletes if hasattr(qs, "model")]
    for model, instances in groups:
        file_fields = [f for f in model._meta.fields if isinstance(f, models.FileField)]
        if not file_fields:
            continue
        for instance in instances:
            for f in file_fields:
                value = getattr(instance, f.name)
                if value:
                    files.append((value.storage, value.name))
    obj.delete()

    def _remove() -> None:
        for storage, name in files:
            try:
                storage.delete(name)
            except OSError:  # pragma: no cover - storage hiccup; logged, row is already gone
                logger.warning("Retention: could not delete a stored file")

    transaction.on_commit(_remove)


def purge(
    *, dry_run: bool, now: dt.datetime | None = None, request: HttpRequest | None = None
) -> dict[str, Any]:
    """Delete every unsuccessful application past its deadline (legal holds skipped). Always audit-logged."""
    candidates = due(now)
    counts = dict.fromkeys(SPECS, 0)
    for c in candidates:
        counts[c.spec.code] += 1
    result: dict[str, Any] = {"dry_run": dry_run, "due": counts, "deleted": 0, "skipped": 0}
    if dry_run:
        result["candidates"] = candidates
        return result
    for c in candidates:
        try:
            with transaction.atomic():
                _erase(c.spec, c.obj)
            result["deleted"] += 1
        except ProtectedError:
            result["skipped"] += 1
            logger.warning("Retention: %s is still referenced by another record; skipped", c.reference)
    log_event(
        AuditLog.Action.PURGE,
        request=request,
        actor_email="" if request else "system:application-retention",
        extra={"applications": counts, "deleted": result["deleted"], "skipped": result["skipped"]},
    )
    return result


# ------------------------------------------------------------------------------------------------ Super Admin
def get_application(kind: str, pk: int) -> tuple[Spec, Any]:
    spec = SPECS.get(kind)
    if spec is None:
        raise ValidationError("Unknown application type.")
    obj = spec.model.objects.filter(pk=pk).first()
    if obj is None:
        raise ValidationError("That application no longer exists.")
    return spec, obj


def set_legal_hold(request: HttpRequest, kind: str, pk: int, *, on: bool, reason: str) -> None:
    if not getattr(request.user, "is_superuser", False):
        raise PermissionDenied
    _spec, obj = get_application(kind, pk)
    reason = (reason or "").strip()
    if on and len(reason) < 5:
        raise ValidationError("Give the reason for the legal hold.")
    obj.legal_hold = on
    obj.legal_hold_reason = reason[:300] if on else ""
    obj.save(update_fields=["legal_hold", "legal_hold_reason", "updated_at"])
    log_event(AuditLog.Action.CHANGE, request=request, obj=obj, extra={"legal_hold": on})


def erase_on_request(request: HttpRequest, kind: str, pk: int, *, reason: str) -> None:
    """Early deletion on the person's valid request (any outcome), unless on legal hold."""
    if not getattr(request.user, "is_superuser", False):
        raise PermissionDenied
    spec, obj = get_application(kind, pk)
    if obj.legal_hold:
        raise ValidationError("This application is on legal hold. Lift the hold first if deletion is lawful.")
    if len((reason or "").strip()) < 5:
        raise ValidationError("Record how the request was received and verified.")
    if spec.code in ("membership", "finance_volunteer") and obj.outcome == OUTCOME.SUCCESSFUL:
        raise ValidationError(
            "This is now a live register record. Use the person's data export / erase request instead."
        )
    reference = f"{spec.label} #{obj.pk}"
    with transaction.atomic():
        _erase(spec, obj)
    log_event(
        AuditLog.Action.PURGE,
        request=request,
        extra={"early_deletion": reference, "reason": reason.strip()[:300]},
    )


class RetentionColumns:
    """Mixin for the application screens: shows when (or whether) an application will be deleted."""

    def retention_deadline(self, obj: Any) -> str:
        return deadline_text(obj)

    retention_deadline.short_description = "Retention deadline"  # type: ignore[attr-defined]
