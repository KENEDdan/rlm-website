"""Background jobs: staff alerts, acknowledgements, retention purge.

Tasks receive only a model label and primary key, never personal data, so nothing sensitive passes
through the Redis broker. The worker loads and decrypts the record itself.
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from celery import shared_task
from django.apps import apps
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .models import SiteSettings

logger = logging.getLogger(__name__)


def _admin_change_url(model_label: str, pk: int) -> str:
    """Where staff open the new submission: its staff-portal screen if it has one, else the admin."""
    from portal.resources import BY_MODEL

    model = apps.get_model(model_label)
    resource = BY_MODEL.get(model)
    if resource is not None:
        return settings.SITE_URL + reverse(
            "portal:resource_detail", args=[resource.department, resource.slug, pk]
        )
    opts = model._meta
    return settings.SITE_URL + reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[pk])


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def notify_staff_new_submission(model_label: str, pk: int) -> bool:
    """'New submission, view in admin'. The email carries NO submission content."""
    site = SiteSettings.load()
    if not site.notification_email:
        return False
    model = apps.get_model(model_label)
    kind = model._meta.verbose_name
    context = {"kind": kind, "ref": f"#{pk}", "url": _admin_change_url(model_label, pk), "site": site}
    send_mail(
        subject=f"New {kind} received ({site.short_name})",
        message=render_to_string("emails/staff_alert.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[site.notification_email],
    )
    return True


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def send_acknowledgement(model_label: str, pk: int, template: str, email_field: str = "email") -> bool:
    """Thank the submitter. Repeats nothing they wrote (emails can be forwarded or intercepted)."""
    model = apps.get_model(model_label)
    obj = model.objects.filter(pk=pk).first()
    if obj is None:
        return False
    address = getattr(obj, email_field, "")
    if not address:
        return False
    site = SiteSettings.load()
    context = {"obj": obj, "site": site, "site_url": settings.SITE_URL}
    subject = render_to_string(f"emails/{template}_subject.txt", context).strip()
    send_mail(
        subject=subject,
        message=render_to_string(f"emails/{template}.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[address],
    )
    return True


RETENTION = {
    "prayer.PrayerRequest": "retention_prayer_days",
    "contact.ContactMessage": "retention_contact_days",
    "registrations.VolunteerApplication": "retention_volunteer_days",
    "registrations.EventRegistration": "retention_event_registration_days",
    "giving.PartnershipEnquiry": "retention_partnership_days",
}


@shared_task
def purge_expired_submissions() -> dict[str, int]:
    """Delete submissions older than the retention periods set in SiteSettings (0 = keep)."""
    site = SiteSettings.load()
    now = timezone.now()
    result: dict[str, int] = {}
    for label, attr in RETENTION.items():
        days = getattr(site, attr)
        if not days:
            continue
        model = apps.get_model(label)
        deleted, _ = model.objects.filter(created_at__lt=now - timedelta(days=days)).delete()
        result[label] = deleted
    # Unconfirmed newsletter sign-ups older than 30 days are removed too.
    subscriber = apps.get_model("newsletter.Subscriber")
    deleted, _ = subscriber.objects.filter(status="pending", created_at__lt=now - timedelta(days=30)).delete()
    result["newsletter.Subscriber(pending)"] = deleted
    if any(result.values()):
        log_event(AuditLog.Action.PURGE, actor_email="system:retention", extra=result)
    logger.info("Retention purge finished: %s", result)
    return result


@shared_task
def purge_unsuccessful_applications() -> dict[str, Any]:
    """Daily: delete unsuccessful applications past their retention deadline (ministry decision 8)."""
    from .retention import purge

    result = purge(dry_run=False)
    logger.info("Application retention: %s", {k: v for k, v in result.items() if k != "candidates"})
    return {k: v for k, v in result.items() if k != "candidates"}


@shared_task
def report_applications_nearing_purge() -> int:
    """Monthly: tell each department head how many of their applications will be deleted soon. Counts only."""
    from portal.models import DepartmentMembership

    from .retention import SPECS, held, nearing

    site = SiteSettings.load()
    soon = nearing()
    on_hold = held()
    sent = 0
    for department in sorted({spec.department for spec in SPECS.values()}):
        rows = []
        for spec in SPECS.values():
            if spec.department != department:
                continue
            n = sum(1 for c in soon if c.spec.code == spec.code)
            h = sum(1 for c in on_hold if c.spec.code == spec.code)
            if n or h:
                rows.append((spec.label, n, h))
        if not rows:
            continue
        heads = DepartmentMembership.objects.filter(
            department__code=department, is_head=True, user__is_active=True
        ).select_related("user")
        recipients = sorted({m.user.email for m in heads if m.user.email})
        if not recipients:
            continue
        context = {
            "rows": rows,
            "days": site.retention_notice_days,
            "site": site,
            "site_url": settings.SITE_URL,
        }
        send_mail(
            subject=render_to_string("emails/retention_report_subject.txt", context).strip(),
            message=render_to_string("emails/retention_report.txt", context),
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )
        sent += 1
    return sent
