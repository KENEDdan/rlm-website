from __future__ import annotations

import hashlib
import logging
from decimal import Decimal, InvalidOperation

from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event
from core.tasks import send_acknowledgement

from .models import Donation, GivingSettings, WebhookEvent
from .providers.base import WebhookOutcome

logger = logging.getLogger(__name__)


def confirm_donation(donation: Donation, request: HttpRequest | None = None) -> bool:
    """Finance confirms money was received. Idempotent: confirming twice changes nothing."""
    with transaction.atomic():
        locked = Donation.objects.select_for_update().get(pk=donation.pk)
        if locked.status == Donation.Status.CONFIRMED:
            return False
        if locked.status not in (Donation.Status.PLEDGED, Donation.Status.PENDING):
            return False
        locked.status = Donation.Status.CONFIRMED
        locked.confirmed_at = timezone.now()
        locked.confirmed_by = getattr(request, "user", None) if request else None
        locked.assign_receipt_number(GivingSettings.load().receipt_prefix)
        locked.save()
    log_event(AuditLog.Action.CHANGE, request=request, obj=locked, extra={"status": "confirmed"})
    if locked.donor_email:
        transaction.on_commit(
            lambda: send_acknowledgement.delay(
                "giving.Donation", locked.pk, "donation_receipt", "donor_email"
            )
        )
    return True


def record_webhook(provider_code: str, outcome: WebhookOutcome, raw_body: bytes) -> tuple[WebhookEvent, bool]:
    """Store the event once. Returns (event, created). A replayed event_id is a no-op."""
    try:
        with transaction.atomic():
            event = WebhookEvent.objects.create(
                provider=provider_code,
                event_id=outcome.event_id,
                event_type=outcome.event_type,
                payload_sha256=hashlib.sha256(raw_body).hexdigest(),
            )
    except IntegrityError:
        return WebhookEvent.objects.get(provider=provider_code, event_id=outcome.event_id), False
    return event, True


def is_actionable(outcome: WebhookOutcome) -> bool:
    return bool(outcome.provider_reference and outcome.new_status)


def _mark_processed(event: WebhookEvent) -> None:
    event.processed = True
    WebhookEvent.objects.filter(pk=event.pk).update(processed=True)


def apply_webhook(event: WebhookEvent, outcome: WebhookOutcome) -> None:
    """Move the matching donation to the reported status (amount/currency must match).

    Only donations created through the SAME provider can be touched, and a gift is only marked
    confirmed when the signed event states an amount that matches the donation.
    """
    if not is_actionable(outcome):
        _mark_processed(event)
        return
    with transaction.atomic():
        donation = (
            Donation.objects.select_for_update()
            .filter(provider=event.provider, provider_reference=outcome.provider_reference)
            .first()
        )
        if donation is None:
            logger.warning("Webhook for unknown provider reference")
            _mark_processed(event)
            return
        if outcome.amount is None and outcome.new_status == Donation.Status.CONFIRMED:
            logger.error("Webhook confirmation without amount for donation %s", donation.pk)
            _mark_processed(event)
            return
        if outcome.amount is not None:
            try:
                if (
                    Decimal(outcome.amount) != donation.amount
                    or (outcome.currency or donation.currency) != donation.currency
                ):
                    logger.error("Webhook amount/currency mismatch for donation %s", donation.pk)
                    _mark_processed(event)
                    return
            except InvalidOperation:
                _mark_processed(event)
                return
        if donation.status == Donation.Status.CONFIRMED and outcome.new_status != Donation.Status.REFUNDED:
            _mark_processed(event)
            return
        donation.status = outcome.new_status
        if outcome.new_status == Donation.Status.CONFIRMED:
            donation.confirmed_at = timezone.now()
            donation.assign_receipt_number(GivingSettings.load().receipt_prefix)
        donation.save()
        _mark_processed(event)
    log_event(
        AuditLog.Action.CHANGE,
        obj=donation,
        actor_email=f"webhook:{event.provider}",
        extra={"status": donation.status},
    )
