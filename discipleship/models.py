"""Discipleship: registrations, disciples, new-convert follow-up, cohorts, mentorship and growth.

Pastoral notes are the most sensitive data in the system: encrypted, visible only to the disciple's assigned
mentor, the Discipleship head and the Founder, and every view of them is audit-logged.
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import RetainedApplication, TimeStampedModel
from core.people import AgeBand, Gender, YesNo, band_for_age
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo


class GrowthArea(models.TextChoices):
    KNOWLEDGE = "knowledge", "Biblical knowledge"
    PRAYER = "prayer", "Prayer and intercession"
    GIFTS = "gifts", "Spiritual gifts"
    CHARACTER = "character", "Christian character"
    EVANGELISM = "evangelism", "Evangelism"
    LEADERSHIP = "leadership", "Leadership and ministry"
    MATURITY = "maturity", "Spiritual maturity"


class Registration(RetainedApplication, TimeStampedModel):
    """Public 'Discipleship Registration' form."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Registration received"
        CONTACTED = "contacted", "Contacted"
        ENROLLED = "enrolled", "Enrolled"
        DECLINED = "declined", "Not taken forward"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    full_name = EncryptedCharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    age = EncryptedCharField(max_length=3, blank=True)
    age_band = models.CharField(
        max_length=10, choices=AgeBand.choices, default=AgeBand.UNKNOWN, editable=False
    )
    is_minor = models.BooleanField(default=False, editable=False, db_index=True)
    nationality = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = EncryptedCharField(max_length=30, verbose_name="phone / WhatsApp")
    email = EncryptedEmailField(blank=True)
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    born_again = EncryptedCharField(max_length=3, choices=YesNo.choices)
    baptized = EncryptedCharField(max_length=3, choices=YesNo.choices, verbose_name="baptized in water")
    attends_church = EncryptedCharField(
        max_length=3, choices=YesNo.choices, verbose_name="currently attending a church"
    )
    journey = EncryptedTextField(verbose_name="spiritual journey and goals")
    growth_areas = models.JSONField(default=list, blank=True)
    guardian_name = EncryptedCharField(max_length=150, blank=True)
    guardian_contact = EncryptedCharField(max_length=100, blank=True)
    guardian_consent = models.BooleanField(default=False)
    consent = models.BooleanField(default=False)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name = "discipleship registration"

    def __str__(self) -> str:
        return f"Registration #{self.pk}"

    @property
    def audit_label(self) -> str:
        return f"discipleship registration #{self.pk}"

    def get_growth_areas_display(self) -> str:
        labels = dict(GrowthArea.choices)
        return ", ".join(str(labels.get(a, a)) for a in self.growth_areas)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        age = int(self.age) if str(self.age).isdigit() else None
        self.age_band = band_for_age(age)
        self.is_minor = self.age_band == AgeBand.UNDER_18
        super().save(*args, **kwargs)


class Disciple(TimeStampedModel):
    class Source(models.TextChoices):
        REGISTRATION = "registration", "Website registration"
        CONVERT = "convert", "New convert (from Missions)"
        MEMBER = "member", "Ministry member"
        STAFF = "staff", "Added by staff"

    class Stage(models.TextChoices):
        NEW = "new", "New"
        IN_CLASS = "in_class", "In a discipleship class"
        MENTORED = "mentored", "Being mentored"
        LEADER_TRACK = "leader_track", "Leadership track"
        COMPLETED = "completed", "Completed the programme"

    full_name = EncryptedCharField(max_length=150)
    phone = EncryptedCharField(max_length=30, blank=True)
    email = EncryptedEmailField(blank=True)
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    age_band = models.CharField(max_length=10, choices=AgeBand.choices, default=AgeBand.UNKNOWN)
    is_minor = models.BooleanField(default=False, editable=False, db_index=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    source = models.CharField(max_length=15, choices=Source.choices, default=Source.STAFF)
    registration = models.OneToOneField(
        Registration,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="disciple",
        editable=False,
    )
    convert = models.OneToOneField(
        "missions.NewConvert",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="disciple",
        editable=False,
    )
    member = models.ForeignKey(
        "membership.Member", null=True, blank=True, on_delete=models.SET_NULL, related_name="disciples"
    )
    growth_areas = models.JSONField(default=list, blank=True)
    stage = models.CharField(max_length=15, choices=Stage.choices, default=Stage.NEW, db_index=True)
    mentor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="mentees",
        help_text="Only the assigned mentor (plus the Discipleship head and Founder) can read pastoral notes.",
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.full_name

    @property
    def audit_label(self) -> str:
        return f"disciple #{self.pk}"

    def get_growth_areas_display(self) -> str:
        labels = dict(GrowthArea.choices)
        return ", ".join(str(labels.get(a, a)) for a in self.growth_areas)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        self.is_minor = self.age_band == AgeBand.UNDER_18
        super().save(*args, **kwargs)


class FollowUp(TimeStampedModel):
    """Missions -> Discipleship handoff for one new convert."""

    class Status(models.TextChoices):
        NEW = "new", "Handed over: not yet contacted"
        CONTACTED = "contacted", "Contacted"
        FIRST_VISIT = "first_visit", "First visit done"
        ENROLLED = "enrolled", "Enrolled in discipleship"
        MILESTONE = "milestone", "Milestone review"
        COMPLETED = "completed", "Follow-up completed"
        LOST = "lost", "Could not be reached"

    OPEN = (Status.NEW, Status.CONTACTED, Status.FIRST_VISIT)

    convert = models.OneToOneField("missions.NewConvert", on_delete=models.CASCADE, related_name="follow_up")
    disciple = models.ForeignKey(
        Disciple, null=True, blank=True, on_delete=models.SET_NULL, related_name="follow_ups", editable=False
    )
    status = models.CharField(max_length=15, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    due_date = models.DateField(null=True, blank=True)
    last_contact = models.DateField(null=True, blank=True)
    notes = EncryptedTextField(blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )
    is_minor = models.BooleanField(default=False, editable=False)

    class Meta:
        ordering: ClassVar = ["status", "due_date"]
        verbose_name = "new-convert follow-up"

    def __str__(self) -> str:
        return f"Follow-up #{self.pk}"

    @property
    def is_overdue(self) -> bool:
        return self.status == self.Status.NEW and bool(self.due_date and self.due_date < timezone.localdate())


class Curriculum(TimeStampedModel):
    title = models.CharField(max_length=200)
    level = models.CharField(max_length=60, blank=True, help_text="e.g. Foundations, Growth, Leadership")
    description = models.TextField(blank=True)
    file = PrivateFileField(
        upload_to=RandomUploadTo("curriculum"), blank=True, verbose_name="study material (PDF)"
    )
    resource = models.ForeignKey(
        "resources.Resource",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        help_text="Optional: a published sermon or devotional.",
    )

    class Meta:
        ordering: ClassVar = ["level", "title"]
        verbose_name = "curriculum / study material"
        verbose_name_plural = "curriculum and study materials"

    def __str__(self) -> str:
        return self.title


class Cohort(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        RUNNING = "running", "Running"
        COMPLETED = "completed", "Completed"

    name = models.CharField(max_length=160)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    curriculum = models.ForeignKey(
        Curriculum, null=True, blank=True, on_delete=models.SET_NULL, related_name="cohorts"
    )
    facilitator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    schedule = models.CharField(max_length=200, blank=True, help_text="e.g. Saturdays 4-6 pm, Juba office")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNED, db_index=True)

    class Meta:
        ordering: ClassVar = ["-start_date"]
        verbose_name = "class / cohort"

    def __str__(self) -> str:
        return self.name


class Enrollment(TimeStampedModel):
    class Status(models.TextChoices):
        ENROLLED = "enrolled", "Enrolled"
        COMPLETED = "completed", "Completed"
        DROPPED = "dropped", "Dropped out"

    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="enrollments")
    disciple = models.ForeignKey(Disciple, on_delete=models.CASCADE, related_name="enrollments")
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ENROLLED)
    enrolled_on = models.DateField(default=timezone.localdate)
    completed_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-enrolled_on"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["cohort", "disciple"], name="unique_enrollment")
        ]

    def __str__(self) -> str:
        return f"{self.disciple} in {self.cohort}"


class ClassSession(TimeStampedModel):
    cohort = models.ForeignKey(Cohort, on_delete=models.CASCADE, related_name="sessions")
    date = models.DateField(default=timezone.localdate)
    topic = models.CharField(max_length=200)

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name = "class session"

    def __str__(self) -> str:
        return f"{self.topic} ({self.date:%d %b})"


class SessionAttendance(TimeStampedModel):
    session = models.ForeignKey(ClassSession, on_delete=models.CASCADE, related_name="attendance")
    disciple = models.ForeignKey(Disciple, on_delete=models.CASCADE, related_name="attendance")
    present = models.BooleanField(default=True)

    class Meta:
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["session", "disciple"], name="unique_session_attendance")
        ]

    def __str__(self) -> str:
        return f"{self.session}: {'present' if self.present else 'absent'}"


class Mentorship(TimeStampedModel):
    mentor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="mentorships")
    disciple = models.ForeignKey(Disciple, on_delete=models.CASCADE, related_name="mentorships")
    start_date = models.DateField(default=timezone.localdate)
    end_date = models.DateField(null=True, blank=True)
    focus = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering: ClassVar = ["-start_date"]

    def __str__(self) -> str:
        return f"{self.mentor} mentoring {self.disciple}"

    @property
    def is_active(self) -> bool:
        return self.end_date is None or self.end_date >= timezone.localdate()


class CheckIn(TimeStampedModel):
    mentorship = models.ForeignKey(Mentorship, on_delete=models.CASCADE, related_name="check_ins")
    date = models.DateField(default=timezone.localdate)
    summary = EncryptedTextField(help_text="Accountability check-in (encrypted).")
    next_step = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name = "accountability check-in"

    def __str__(self) -> str:
        return f"Check-in {self.date:%d %b %Y}"


class PastoralNote(TimeStampedModel):
    disciple = models.ForeignKey(Disciple, on_delete=models.CASCADE, related_name="pastoral_notes")
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    note = EncryptedTextField()

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"Pastoral note #{self.pk}"

    @property
    def audit_label(self) -> str:
        return f"pastoral note #{self.pk}"


SCORE = [MinValueValidator(1), MaxValueValidator(5)]


class Assessment(TimeStampedModel):
    disciple = models.ForeignKey(Disciple, on_delete=models.CASCADE, related_name="assessments")
    date = models.DateField(default=timezone.localdate)
    assessed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    knowledge = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="biblical knowledge (1-5)")
    prayer = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="prayer and intercession (1-5)")
    gifts = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="spiritual gifts (1-5)")
    character = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="Christian character (1-5)")
    evangelism = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="evangelism (1-5)")
    leadership = models.PositiveSmallIntegerField(
        validators=SCORE, verbose_name="leadership and ministry (1-5)"
    )
    maturity = models.PositiveSmallIntegerField(validators=SCORE, verbose_name="spiritual maturity (1-5)")
    notes = EncryptedTextField(blank=True)

    AREAS: ClassVar = ["knowledge", "prayer", "gifts", "character", "evangelism", "leadership", "maturity"]

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name = "spiritual growth assessment"

    def __str__(self) -> str:
        return f"Assessment {self.date:%d %b %Y}"

    @property
    def average(self) -> float:
        return round(sum(getattr(self, a) for a in self.AREAS) / len(self.AREAS), 1)


class LeaderCandidate(TimeStampedModel):
    class Stage(models.TextChoices):
        IDENTIFIED = "identified", "Identified"
        TRAINING = "training", "In training"
        APPRENTICE = "apprentice", "Serving as apprentice"
        COMMISSIONED = "commissioned", "Commissioned"

    disciple = models.OneToOneField(Disciple, on_delete=models.CASCADE, related_name="leader_track")
    stage = models.CharField(max_length=15, choices=Stage.choices, default=Stage.IDENTIFIED)
    ministry_area = models.CharField(max_length=120, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["stage"]
        verbose_name = "emerging leader"

    def __str__(self) -> str:
        return f"{self.disciple} ({self.get_stage_display()})"


def default_follow_up_due(decision_date: Any) -> Any:
    return (decision_date or timezone.localdate()) + timedelta(days=7)
