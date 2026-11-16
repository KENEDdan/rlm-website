"""Data-subject requests (CLAUDE.md rule 13): find, export or erase everything held about one person.

People are matched by the HMAC blind index of their email address, so no plaintext search is needed.
Donations are ANONYMISED instead of deleted: the financial record (amount, date, receipt number) must be
kept for accounting, but nothing in it identifies the donor any more.
"""

from __future__ import annotations

import json
from typing import Any

from django.apps import apps
from django.core.serializers.json import DjangoJSONEncoder
from django.db import models, transaction

from audit.models import AuditLog
from audit.services import log_event
from core.crypto import blind_index

# (model label, blind-index field). Add a row here when a new model stores a person's email.
PERSON_SOURCES: list[tuple[str, str]] = [
    ("prayer.PrayerRequest", "email_hash"),
    ("contact.ContactMessage", "email_hash"),
    ("registrations.VolunteerApplication", "email_hash"),
    ("registrations.EventRegistration", "email_hash"),
    ("giving.PartnershipEnquiry", "email_hash"),
    ("newsletter.Subscriber", "email_hash"),
    ("giving.Donation", "donor_email_hash"),
]
ANONYMISE_INSTEAD_OF_DELETE: dict[str, dict[str, Any]] = {
    "giving.Donation": {
        "donor_name": "",
        "donor_email": "",
        "donor_phone": "",
        "donor_message": "",
        "transfer_reference": "",
        "is_anonymous": True,
    },
}


def find_person(email: str) -> dict[str, models.QuerySet]:
    digest = blind_index(email)
    if not digest:
        return {}
    return {
        label: apps.get_model(label)._default_manager.filter(**{field: digest})
        for label, field in PERSON_SOURCES
    }


def _row(obj: models.Model) -> dict[str, Any]:
    return {
        f.name: getattr(obj, f.attname)
        for f in obj._meta.concrete_fields
        if not f.name.endswith("_hash")  # keyed hashes mean nothing to the person
    }


def export_person(email: str, *, actor: str) -> str:
    """JSON document with every record held about ``email`` (decrypted). Audit-logged."""
    data = {label: [_row(obj) for obj in qs] for label, qs in find_person(email).items()}
    data = {label: rows for label, rows in data.items() if rows}
    log_event(
        AuditLog.Action.PRIVACY_EXPORT,
        actor_email=actor,
        extra={"records": {label: len(rows) for label, rows in data.items()}},
    )
    return json.dumps(data, cls=DjangoJSONEncoder, indent=2, ensure_ascii=False)


def erase_person(email: str, *, actor: str) -> dict[str, int]:
    """Delete (or anonymise) every record held about ``email``. Audit-logged without the address."""
    result: dict[str, int] = {}
    with transaction.atomic():
        for label, qs in find_person(email).items():
            blank = ANONYMISE_INSTEAD_OF_DELETE.get(label)
            if blank is None:
                result[label] = qs.delete()[0]
                continue
            count = 0
            for obj in qs.select_for_update():
                for name, value in blank.items():
                    setattr(obj, name, value)
                obj.save()  # save() recomputes the blind index from the now-empty email
                count += 1
            result[label] = count
        log_event(AuditLog.Action.PRIVACY_ERASE, actor_email=actor, extra={"records": result})
    return result
