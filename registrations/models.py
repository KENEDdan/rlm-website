from __future__ import annotations

from typing import Any, ClassVar

from django.db import models

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import SubmissionModel
from core.site_text import option_label


class VolunteerApplication(SubmissionModel):
    full_name = EncryptedCharField(max_length=150)
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30)
    country = models.CharField(max_length=100)
    location = models.CharField(max_length=120, help_text="City or town")
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="volunteers"
    )
    church_affiliation = EncryptedCharField(max_length=200, blank=True)
    interests = models.JSONField(default=list, blank=True)
    skills = EncryptedTextField(blank=True)
    previous_experience = EncryptedTextField(blank=True)
    testimony = EncryptedTextField(blank=True)
    # Values come from the admin-managed lists (core.FormOption); labels via get_*_display below.
    availability = models.CharField(max_length=20)
    consent = models.BooleanField(default=False)
    internal_notes = EncryptedTextField(blank=True, help_text="Visible to staff only.")

    class Meta(SubmissionModel.Meta):
        verbose_name = "volunteer application"
        permissions: ClassVar = [("export_volunteerapplication", "Can export volunteer applications")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)

    @property
    def interest_labels(self) -> list[str]:
        return [option_label("volunteer_interest", i) for i in self.interests]

    def get_interests_display(self) -> str:
        return ", ".join(self.interest_labels)

    def get_availability_display(self) -> str:
        return option_label("volunteer_availability", self.availability)


class EventRegistration(SubmissionModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed"
        CANCELLED = "cancelled", "Cancelled"
        ATTENDED = "attended", "Attended"

    event = models.ForeignKey("events.Event", on_delete=models.CASCADE, related_name="registrations")
    full_name = EncryptedCharField(max_length=150)
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    attendees = models.PositiveSmallIntegerField(default=1)
    notes = EncryptedTextField(blank=True, help_text="Accessibility needs or questions.")
    registration_status = models.CharField(max_length=20, choices=Status.choices, default=Status.CONFIRMED)
    consent = models.BooleanField(default=False)

    class Meta(SubmissionModel.Meta):
        verbose_name = "event registration"
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["event", "email_hash"], name="unique_registration_per_event")
        ]
        permissions: ClassVar = [("export_eventregistration", "Can export event registrations")]

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
