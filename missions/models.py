"""Missions & Outreach: campaigns, communities, teams, field reports and new converts.

A decision for Christ recorded here becomes a ``NewConvert``; the Discipleship app turns every convert into a
follow-up task (the cross-department handoff, ``discipleship.signals``).
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import TimeStampedModel
from core.people import AgeBand, Gender
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo
from finance.models import BudgetApproval


class Community(TimeStampedModel):
    class Kind(models.TextChoices):
        COMMUNITY = "community", "Community / village"
        SCHOOL = "school", "School"
        HOSPITAL = "hospital", "Hospital"
        PRISON = "prison", "Prison"
        CHURCH = "church", "Church"
        INSTITUTION = "institution", "Other institution"

    class Status(models.TextChoices):
        TARGET = "target", "Target (not yet reached)"
        ENGAGED = "engaged", "Engaged"
        ESTABLISHED = "established", "Fellowship established"

    class Expansion(models.TextChoices):
        NONE = "none", "No plans"
        IDENTIFIED = "identified", "Opportunity identified"
        ASSESSING = "assessing", "Being assessed"
        PLANNED = "planned", "Planned"
        LAUNCHED = "launched", "Launched"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=15, choices=Kind.choices, default=Kind.COMMUNITY)
    country = models.CharField(max_length=100, default="South Sudan")
    region = models.CharField(max_length=120, blank=True, help_text="State / county")
    location = models.CharField(max_length=160, blank=True, help_text="Town, payam or landmark")
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.TARGET)
    opportunity = models.CharField(
        max_length=12, choices=Expansion.choices, default=Expansion.NONE, verbose_name="expansion opportunity"
    )
    population = models.PositiveIntegerField(null=True, blank=True, help_text="Rough estimate")
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["name"]
        verbose_name_plural = "communities"

    def __str__(self) -> str:
        return f"{self.name}{f', {self.location}' if self.location else ''}"


class CommunityContact(TimeStampedModel):
    class Role(models.TextChoices):
        PASTOR = "pastor", "Pastor / church leader"
        LEADER = "leader", "Community leader / chief"
        HEADTEACHER = "headteacher", "Head teacher"
        CHAPLAIN = "chaplain", "Chaplain"
        OFFICIAL = "official", "Government / institution official"
        OTHER = "other", "Other"

    community = models.ForeignKey(Community, on_delete=models.CASCADE, related_name="contacts")
    role = models.CharField(max_length=15, choices=Role.choices)
    name = EncryptedCharField(max_length=150)
    phone = EncryptedCharField(max_length=30, blank=True)
    email = EncryptedEmailField(blank=True)
    church_or_office = models.CharField(max_length=200, blank=True)
    notes = EncryptedTextField(blank=True)

    class Meta:
        ordering: ClassVar = ["role"]

    def __str__(self) -> str:
        return f"{self.get_role_display()}: {self.name}"


class Team(TimeStampedModel):
    name = models.CharField(max_length=120)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    leader = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    focus = models.CharField(max_length=160, blank=True, help_text="e.g. Schools, Prisons, Open-air")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["name"]
        verbose_name = "evangelism team"

    def __str__(self) -> str:
        return self.name


class TeamMember(TimeStampedModel):
    team = models.ForeignKey(Team, on_delete=models.CASCADE, related_name="members")
    name = EncryptedCharField(max_length=150)
    phone = EncryptedCharField(max_length=30, blank=True)
    role = models.CharField(max_length=80, blank=True, help_text="e.g. Preacher, Counsellor, Worship, Driver")
    is_volunteer = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["role"]
        verbose_name = "team member / volunteer"

    def __str__(self) -> str:
        return f"{self.name}{f' ({self.role})' if self.role else ''}"


class Campaign(BudgetApproval, TimeStampedModel):
    class Kind(models.TextChoices):
        CRUSADE = "crusade", "Crusade"
        OPEN_AIR = "open_air", "Open-air meeting"
        SCHOOL = "school", "School visit"
        HOSPITAL = "hospital", "Hospital visit"
        PRISON = "prison", "Prison visit"
        COMMUNITY = "community", "Community visit"
        DOOR_TO_DOOR = "door_to_door", "Door-to-door"
        MISSION_TRIP = "mission_trip", "Mission trip"

    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        APPROVED = "approved", "Approved"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"
        CANCELLED = "cancelled", "Cancelled"

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=15, choices=Kind.choices)
    community = models.ForeignKey(
        Community, null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns"
    )
    location = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    team = models.ForeignKey(Team, null=True, blank=True, on_delete=models.SET_NULL, related_name="campaigns")
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    objectives = models.TextField(blank=True)
    budget_request = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    materials = models.TextField(blank=True, help_text="Bibles, tracts, sound system, tents…")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED, db_index=True)

    class Meta:
        ordering: ClassVar = ["-start_date"]
        verbose_name = "outreach campaign"

    def __str__(self) -> str:
        return f"{self.title} ({self.start_date:%d %b %Y})"


class FieldReport(TimeStampedModel):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="reports")
    report_date = models.DateField(default=timezone.localdate)
    souls_reached = models.PositiveIntegerField(default=0, help_text="People who heard the Gospel")
    decisions = models.PositiveIntegerField(default=0, help_text="Decisions for Christ")
    challenges = models.TextField(blank=True)
    testimonies = EncryptedTextField(
        blank=True, help_text="Private. Media publishes only with written consent."
    )
    submitted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        ordering: ClassVar = ["-report_date"]

    def __str__(self) -> str:
        return f"Report {self.report_date:%d %b %Y} · {self.campaign.title}"


class FieldPhoto(TimeStampedModel):
    report = models.ForeignKey(FieldReport, on_delete=models.CASCADE, related_name="photos")
    image = PrivateFileField(upload_to=RandomUploadTo("field"), images_only=True)
    caption = models.CharField(max_length=200, blank=True)
    people_consented = models.BooleanField(
        default=False, help_text="Identifiable people agreed to the photo being used."
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.caption or f"Photo #{self.pk}"


class NewConvert(TimeStampedModel):
    """A person who made a decision for Christ. Handed to Discipleship for follow-up automatically."""

    campaign = models.ForeignKey(
        Campaign, null=True, blank=True, on_delete=models.SET_NULL, related_name="converts"
    )
    decision_date = models.DateField(default=timezone.localdate)
    full_name = EncryptedCharField(max_length=150)
    phone = EncryptedCharField(max_length=30, blank=True)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    age_band = models.CharField(max_length=10, choices=AgeBand.choices, default=AgeBand.UNKNOWN)
    is_minor = models.BooleanField(default=False, editable=False, db_index=True)
    location = models.CharField(max_length=160, blank=True, help_text="Where they live (village / area)")
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    consent_to_contact = models.BooleanField(
        default=False, help_text="They agreed to be contacted for follow-up."
    )
    guardian_contact = EncryptedCharField(max_length=100, blank=True, help_text="Required for under-18s.")
    notes = EncryptedTextField(blank=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        ordering: ClassVar = ["-decision_date"]

    def __str__(self) -> str:
        return f"New convert #{self.pk}"

    @property
    def audit_label(self) -> str:
        return f"new convert #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.is_minor = self.age_band == AgeBand.UNDER_18
        if not self.branch_id and self.campaign_id:
            self.branch_id = self.campaign.branch_id
        super().save(*args, **kwargs)
