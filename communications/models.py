"""Media & Communications: content calendar, design requests, event coverage and (manual) social reach.

The public media archive itself (albums, photos, videos, testimonies, hero slides) lives in the existing
``media_library`` and ``core`` apps; the portal manages those records directly (communications.portal_config).
No third-party tracking scripts: social figures are typed in by the team from each platform's own insights.
"""

from __future__ import annotations

from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo
from core.validators import validate_safe_link


class Channel(models.TextChoices):
    WEBSITE = "website", "Website"
    FACEBOOK = "facebook", "Facebook"
    INSTAGRAM = "instagram", "Instagram"
    TIKTOK = "tiktok", "TikTok"
    YOUTUBE = "youtube", "YouTube"
    WHATSAPP = "whatsapp", "WhatsApp"


class ContentItem(TimeStampedModel):
    class Stage(models.TextChoices):
        IDEA = "idea", "Idea"
        PRODUCTION = "production", "In production"
        REVIEW = "review", "In review"
        PUBLISHED = "published", "Published"

    title = models.CharField(max_length=200)
    channel = models.CharField(max_length=12, choices=Channel.choices)
    stage = models.CharField(max_length=12, choices=Stage.choices, default=Stage.IDEA, db_index=True)
    planned_date = models.DateField(default=timezone.localdate, db_index=True)
    published_on = models.DateField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="content_items"
    )
    link = models.CharField(
        max_length=300,
        blank=True,
        validators=[validate_safe_link],
        help_text="Link to the published post (https://)",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["planned_date"]
        verbose_name = "content calendar item"

    def __str__(self) -> str:
        return f"{self.title} ({self.get_channel_display()})"

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.stage == self.Stage.PUBLISHED and not self.published_on:
            self.published_on = timezone.localdate()
        super().save(*args, **kwargs)


class DesignRequest(TimeStampedModel):
    class Kind(models.TextChoices):
        POSTER = "poster", "Poster"
        BANNER = "banner", "Banner"
        FLYER = "flyer", "Flyer"
        SOCIAL = "social", "Social media graphic"
        VIDEO = "video", "Video"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        NEW = "new", "New"
        IN_PROGRESS = "in_progress", "In progress"
        REVIEW = "review", "Awaiting the requester's review"
        DELIVERED = "delivered", "Delivered"
        CANCELLED = "cancelled", "Cancelled"

    OPEN = (Status.NEW, Status.IN_PROGRESS, Status.REVIEW)

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    requesting_department = models.ForeignKey(
        "portal.Department", on_delete=models.PROTECT, related_name="design_requests"
    )
    needed_by = models.DateField()
    brief = models.TextField(help_text="What it is for, the wording, sizes and where it will be used.")
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.NEW, db_index=True)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    artwork = PrivateFileField(
        upload_to=RandomUploadTo("design"), blank=True, help_text="Final file (PDF or image)"
    )

    class Meta:
        ordering: ClassVar = ["needed_by"]

    def __str__(self) -> str:
        return f"{self.get_kind_display()}: {self.title}"

    @property
    def is_late(self) -> bool:
        return self.status in self.OPEN and self.needed_by < timezone.localdate()


class EventCoverage(TimeStampedModel):
    class Status(models.TextChoices):
        PLANNED = "planned", "Planned"
        COVERED = "covered", "Covered"
        NOT_COVERED = "not_covered", "Not covered"

    event = models.OneToOneField("events.Event", on_delete=models.CASCADE, related_name="coverage")
    photographer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    videographer = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    live_stream = models.BooleanField(default=False)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PLANNED)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["event__start"]
        verbose_name = "event coverage plan"

    def __str__(self) -> str:
        return f"Coverage: {self.event}"


class SocialReach(TimeStampedModel):
    month = models.DateField(help_text="First day of the month")
    channel = models.CharField(max_length=12, choices=Channel.choices)
    followers = models.PositiveIntegerField(null=True, blank=True)
    reach = models.PositiveIntegerField(
        null=True, blank=True, help_text="People reached that month (platform insights)"
    )
    engagements = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-month", "channel"]
        verbose_name = "social reach (manual figures)"
        verbose_name_plural = "social reach (manual figures)"
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["month", "channel"], name="unique_reach_month_channel")
        ]

    def __str__(self) -> str:
        return f"{self.get_channel_display()} {self.month:%b %Y}"

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        self.month = self.month.replace(day=1)
        super().save(*args, **kwargs)
