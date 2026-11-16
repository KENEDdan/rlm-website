from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import SubmissionModel


class PrayerRequest(SubmissionModel):
    """The most sensitive data on the site: every personal field is encrypted at rest."""

    name = EncryptedCharField(max_length=150, blank=True)
    email = EncryptedEmailField(blank=True)
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    request_text = EncryptedTextField()
    keep_confidential = models.BooleanField(
        default=True, help_text="Only the pastoral/prayer team should read this request."
    )
    wants_contact = models.BooleanField(default=False)
    consent = models.BooleanField(default=False)
    internal_notes = EncryptedTextField(blank=True)

    class Meta(SubmissionModel.Meta):
        verbose_name = "prayer request"
        permissions: ClassVar = [("export_prayerrequest", "Can export prayer requests")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
