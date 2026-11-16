from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import SubmissionModel


class ContactMessage(SubmissionModel):
    class Topic(models.TextChoices):
        GENERAL = "general", "General enquiry"
        EVENTS = "events", "Events"
        PARTNERSHIP = "partnership", "Partnership"
        MEDIA = "media", "Media & invitations"
        OTHER = "other", "Other"

    name = EncryptedCharField(max_length=150)
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    topic = models.CharField(max_length=20, choices=Topic.choices, default=Topic.GENERAL)
    subject = EncryptedCharField(max_length=150)
    message = EncryptedTextField()
    consent = models.BooleanField(default=False)
    internal_notes = EncryptedTextField(blank=True)

    class Meta(SubmissionModel.Meta):
        verbose_name = "contact message"
        permissions: ClassVar = [("export_contactmessage", "Can export contact messages")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
