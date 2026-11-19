"""Membership Administration: register, admission workflow, participation, welfare and communications.

Personal and faith data is encrypted at rest (CLAUDE.md rule 3). ``age_band`` and ``is_minor`` are kept in
plain text because the dashboard and the minors rule need to filter on them; they reveal far less than the
date of birth, which is encrypted.
"""

from __future__ import annotations

from datetime import date
from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import TimeStampedModel
from core.people import AgeBand, Gender, YesNo, age_on, band_for_age, parse_iso_date
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo


class Member(TimeStampedModel):
    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Application received"
        UNDER_REVIEW = "under_review", "Under review"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Not accepted"
        ORIENTATION = "orientation", "In orientation"
        INTEGRATION = "integration", "Being integrated"
        ACTIVE = "active", "Active"
        INACTIVE = "inactive", "Inactive"
        TRANSFERRED = "transferred", "Transferred"

    class Source(models.TextChoices):
        WEBSITE = "website", "Website form"
        STAFF = "staff", "Entered by staff"

    PENDING = (Status.SUBMITTED, Status.UNDER_REVIEW)
    CURRENT = (Status.APPROVED, Status.ORIENTATION, Status.INTEGRATION, Status.ACTIVE)

    member_number = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    source = models.CharField(max_length=10, choices=Source.choices, default=Source.STAFF, editable=False)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="members"
    )
    # A. Personal information
    full_name = EncryptedCharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    date_of_birth = EncryptedCharField(max_length=10, blank=True, help_text="YYYY-MM-DD")
    age_band = models.CharField(
        max_length=10, choices=AgeBand.choices, default=AgeBand.UNKNOWN, editable=False
    )
    is_minor = models.BooleanField(default=False, editable=False, db_index=True)
    nationality = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = EncryptedCharField(max_length=30, blank=True, verbose_name="phone / WhatsApp")
    email = EncryptedEmailField(blank=True)
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    occupation = EncryptedCharField(max_length=150, blank=True)
    # B. Christian background
    born_again = EncryptedCharField(max_length=3, blank=True, choices=YesNo.choices)
    church_attended = EncryptedCharField(max_length=200, blank=True, verbose_name="church attended")
    years_christian = EncryptedCharField(max_length=60, blank=True, verbose_name="how long a Christian")
    # C. Personal statement
    testimony = EncryptedTextField(blank=True, verbose_name="personal statement and testimony")
    talents = EncryptedTextField(blank=True, verbose_name="talents, skills and gifts")
    declaration = models.BooleanField(
        default=False, help_text="Agreed to uphold the vision, mission and values."
    )
    consent = models.BooleanField(default=False)
    comms_opt_in = models.BooleanField(
        default=False,
        verbose_name="agreed to receive ministry announcements",
        help_text="Bulk messages go only to these.",
    )
    # Minors (under 18): guardian details and consent are required before approval.
    guardian_name = EncryptedCharField(max_length=150, blank=True)
    guardian_contact = EncryptedCharField(max_length=100, blank=True)
    guardian_consent = models.BooleanField(default=False)
    # Admission
    join_date = models.DateField(null=True, blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)
    decision_note = EncryptedTextField(blank=True, editable=False)
    orientation_date = models.DateField(null=True, blank=True)
    transferred_to = models.CharField(max_length=150, blank=True)
    internal_notes = EncryptedTextField(blank=True, help_text="Staff only.")
    engagement_score = models.PositiveSmallIntegerField(default=0, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        permissions: ClassVar = [("export_member", "Can export members")]

    def __str__(self) -> str:
        return f"{self.member_number or 'Applicant'} · {self.full_name}"

    @property
    def audit_label(self) -> str:
        return f"member #{self.pk}"

    @property
    def birth_date(self) -> date | None:
        return parse_iso_date(self.date_of_birth)

    @property
    def age(self) -> int | None:
        return age_on(self.birth_date)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        self.age_band = band_for_age(self.age)
        self.is_minor = self.age_band == AgeBand.UNDER_18
        super().save(*args, **kwargs)
        if self.member_number is None and self.status not in (*self.PENDING, self.Status.REJECTED):
            type(self).objects.filter(pk=self.pk).update(member_number=f"RLM-{self.pk:06d}")
            self.member_number = f"RLM-{self.pk:06d}"


class ServiceRecord(TimeStampedModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="service_records")
    ministry_area = models.CharField(max_length=120, help_text="e.g. Choir, Ushering, Youth, Media")
    role = models.CharField(max_length=120, blank=True)
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.ministry_area} ({self.start_date:%b %Y})"

    @property
    def is_current(self) -> bool:
        return self.end_date is None or self.end_date >= timezone.localdate()


class Activity(TimeStampedModel):
    class Kind(models.TextChoices):
        SERVICE = "service", "Worship service"
        FELLOWSHIP = "fellowship", "Fellowship"
        MEETING = "meeting", "Meeting"
        TRAINING = "training", "Training / class"
        OUTREACH = "outreach", "Outreach"
        OTHER = "other", "Other"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SERVICE)
    date = models.DateField(default=timezone.localdate, db_index=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    event = models.ForeignKey(
        "events.Event",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional: the public event.",
    )

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name_plural = "activities"

    def __str__(self) -> str:
        return f"{self.name} ({self.date:%d %b %Y})"


class Attendance(TimeStampedModel):
    activity = models.ForeignKey(Activity, on_delete=models.CASCADE, related_name="attendance")
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="attendance")
    present = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["-activity__date"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["activity", "member"], name="unique_attendance")
        ]

    def __str__(self) -> str:
        return f"{self.activity}: {'present' if self.present else 'absent'}"


class WelfareCase(TimeStampedModel):
    class Category(models.TextChoices):
        BEREAVEMENT = "bereavement", "Bereavement"
        MEDICAL = "medical", "Medical"
        FINANCIAL = "financial", "Financial hardship"
        FAMILY = "family", "Family"
        ADMIN = "admin", "Administrative concern"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        IN_PROGRESS = "in_progress", "In progress"
        CLOSED = "closed", "Closed"

    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="welfare_cases")
    category = models.CharField(max_length=20, choices=Category.choices)
    summary = EncryptedTextField(help_text="Encrypted. Only what is needed to help.")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.OPEN, db_index=True)
    opened_on = models.DateField(default=timezone.localdate)
    closed_on = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )

    class Meta:
        ordering: ClassVar = ["status", "-opened_on"]

    def __str__(self) -> str:
        return f"Welfare case #{self.pk} ({self.get_category_display()})"


class MemberDocument(TimeStampedModel):
    member = models.ForeignKey(Member, on_delete=models.CASCADE, related_name="documents")
    title = models.CharField(max_length=160)
    file = PrivateFileField(upload_to=RandomUploadTo("members"))

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.title


# ------------------------------------------------------------------------------------------ communications
class Announcement(TimeStampedModel):
    title = models.CharField(max_length=160)
    body = models.TextField()
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, help_text="Empty = all branches."
    )
    published_on = models.DateField(default=timezone.localdate)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        ordering: ClassVar = ["-published_on"]

    def __str__(self) -> str:
        return self.title


class MeetingMinutes(TimeStampedModel):
    title = models.CharField(max_length=160)
    meeting_date = models.DateField(default=timezone.localdate)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    attendees = models.TextField(blank=True, help_text="Names or roles present.")
    minutes = models.TextField()
    action_points = models.TextField(blank=True)
    file = PrivateFileField(upload_to=RandomUploadTo("minutes"), blank=True)

    class Meta:
        ordering: ClassVar = ["-meeting_date"]
        verbose_name_plural = "meeting minutes"

    def __str__(self) -> str:
        return f"{self.title} ({self.meeting_date:%d %b %Y})"


class Correspondence(TimeStampedModel):
    class Direction(models.TextChoices):
        INCOMING = "in", "Incoming"
        OUTGOING = "out", "Outgoing"

    direction = models.CharField(max_length=3, choices=Direction.choices)
    date = models.DateField(default=timezone.localdate)
    reference = models.CharField(max_length=60, blank=True)
    counterparty = models.CharField(max_length=200, help_text="Organisation or office")
    subject = models.CharField(max_length=200)
    summary = models.TextField(blank=True)
    file = PrivateFileField(upload_to=RandomUploadTo("correspondence"), blank=True)

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name_plural = "correspondence"

    def __str__(self) -> str:
        return f"{self.get_direction_display()}: {self.subject}"


class BulkMessage(TimeStampedModel):
    class Channel(models.TextChoices):
        EMAIL = "email", "Email"
        WHATSAPP = "whatsapp", "WhatsApp links (sent by hand)"

    class Audience(models.TextChoices):
        ACTIVE = "active", "Active members"
        CURRENT = "current", "All current members (incl. orientation/integration)"

    subject = models.CharField(max_length=160)
    body = models.TextField(help_text="Do not include anyone's personal details.")
    channel = models.CharField(max_length=10, choices=Channel.choices, default=Channel.EMAIL)
    audience = models.CharField(max_length=10, choices=Audience.choices, default=Audience.ACTIVE)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, help_text="Empty = all branches."
    )
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    sent_at = models.DateTimeField(null=True, blank=True, editable=False)
    recipient_count = models.PositiveIntegerField(default=0, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.subject
