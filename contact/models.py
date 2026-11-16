from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import SubmissionModel
from core.site_text import option_label


class ContactMessage(SubmissionModel):
    name = EncryptedCharField(max_length=150)
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    topic = models.CharField(max_length=20, default="general")  # admin-managed list "contact_topic"
    subject = EncryptedCharField(max_length=150)
    message = EncryptedTextField()
    consent = models.BooleanField(default=False)
    internal_notes = EncryptedTextField(blank=True)

    class Meta(SubmissionModel.Meta):
        verbose_name = "contact message"
        permissions: ClassVar = [("export_contactmessage", "Can export contact messages")]

    def get_topic_display(self) -> str:
        return option_label("contact_topic", self.topic)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
