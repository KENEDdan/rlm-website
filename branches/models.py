from __future__ import annotations

from typing import ClassVar

from django.db import models
from django.urls import reverse

from core.models import PublishableModel, TimeStampedModel, phone_validator
from core.uploads import RandomUploadTo, SafeImageField


class Country(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    code = models.CharField(max_length=2, unique=True, help_text="ISO 3166-1 alpha-2, e.g. SS")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "name"]
        verbose_name_plural = "countries"

    def __str__(self) -> str:
        return self.name


class Branch(PublishableModel):
    """A ministry branch. Adding a new branch or country needs no code, only a new row."""

    country = models.ForeignKey(Country, on_delete=models.PROTECT, related_name="branches")
    name = models.CharField(max_length=120)
    city = models.CharField(max_length=120, blank=True)
    summary = models.CharField(max_length=300, blank=True)
    description = models.TextField(blank=True)
    activities = models.TextField(blank=True, help_text="One activity per line.")
    meeting_times = models.TextField(blank=True, help_text="One per line, e.g. 'Sunday service: 9:00 AM'.")
    contact_email = models.EmailField(blank=True)
    contact_phone = models.CharField(max_length=30, blank=True, validators=[phone_validator])
    address = models.TextField(blank=True)
    map_url = models.URLField(blank=True, help_text="Optional link to a map (opens in a new tab).")
    image = SafeImageField(upload_to=RandomUploadTo("branches"), blank=True)
    image_alt = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["country__order", "order", "name"]
        verbose_name_plural = "branches"

    def __str__(self) -> str:
        return self.name

    def get_absolute_url(self) -> str:
        return reverse("branches:detail", args=[self.slug])

    @property
    def activity_list(self) -> list[str]:
        return [a.strip() for a in self.activities.splitlines() if a.strip()]

    @property
    def meeting_list(self) -> list[str]:
        return [a.strip() for a in self.meeting_times.splitlines() if a.strip()]
