from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.urls import reverse
from django.utils import timezone

from core.models import PublishableModel, PublishedQuerySet
from core.uploads import RandomUploadTo, SafeImageField


class EventQuerySet(PublishedQuerySet):
    def upcoming(self) -> EventQuerySet:
        return self.published().filter(end__gte=timezone.now()).order_by("start")

    def past(self) -> EventQuerySet:
        return self.published().filter(end__lt=timezone.now()).order_by("-start")


class Event(PublishableModel):
    title = models.CharField(max_length=160)
    summary = models.CharField(max_length=300)
    description = models.TextField(blank=True)
    program = models.ForeignKey(
        "programs.Program", null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="events",
        help_text="Leave empty for ministry-wide events.",
    )
    department = models.ForeignKey(
        "leadership.Department", null=True, blank=True, on_delete=models.SET_NULL, related_name="events"
    )
    start = models.DateTimeField(db_index=True)
    end = models.DateTimeField()
    venue = models.CharField(max_length=200, blank=True)
    address = models.CharField(max_length=300, blank=True)
    registration_open = models.BooleanField(default=False)
    registration_deadline = models.DateTimeField(null=True, blank=True)
    capacity = models.PositiveIntegerField(null=True, blank=True, help_text="Leave empty for unlimited.")
    poster = SafeImageField(upload_to=RandomUploadTo("events"), blank=True)
    poster_alt = models.CharField(max_length=200, blank=True)

    objects = EventQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-start"]
        permissions: ClassVar = []

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if self.start and self.end and self.end < self.start:
            raise ValidationError({"end": "The event must end after it starts."})

    def get_absolute_url(self) -> str:
        return reverse("events:detail", args=[self.slug])

    @property
    def is_upcoming(self) -> bool:
        return self.end >= timezone.now()

    @property
    def seats_taken(self) -> int:
        from django.db.models import Sum

        total = self.registrations.exclude(registration_status="cancelled").aggregate(n=Sum("attendees"))["n"]
        return total or 0

    @property
    def spots_left(self) -> int | None:
        if self.capacity is None:
            return None
        return max(self.capacity - self.seats_taken, 0)

    @property
    def can_register(self) -> bool:
        now = timezone.now()
        if not (self.is_published and self.registration_open and self.end >= now):
            return False
        if self.registration_deadline and now > self.registration_deadline:
            return False
        return self.spots_left is None or self.spots_left > 0
