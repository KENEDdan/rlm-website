from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField
from core.models import TimeStampedModel


class Subscriber(TimeStampedModel):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending confirmation"
        CONFIRMED = "confirmed", "Confirmed"
        UNSUBSCRIBED = "unsubscribed", "Unsubscribed"

    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, unique=True, editable=False)
    name = EncryptedCharField(max_length=150, blank=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING, db_index=True)
    confirmed_at = models.DateTimeField(null=True, blank=True)
    unsubscribed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        permissions: ClassVar = [("export_subscriber", "Can export newsletter subscribers")]

    def __str__(self) -> str:
        return self.audit_label

    @property
    def audit_label(self) -> str:
        return f"subscriber #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
