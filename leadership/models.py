from __future__ import annotations

from typing import ClassVar

from django.db import models

from core.models import TimeStampedModel
from core.uploads import RandomUploadTo, SafeImageField


class Department(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class LeaderQuerySet(models.QuerySet):
    def published(self) -> LeaderQuerySet:
        return self.filter(is_published=True, confirmation_status=Leader.Status.CONFIRMED)


class Leader(TimeStampedModel):
    class Status(models.TextChoices):
        CONFIRMED = "confirmed", "Confirmed by leadership"
        TO_BE_CONFIRMED = "tbc", "To be confirmed by leadership"

    name = models.CharField(max_length=150)
    role_title = models.CharField(max_length=150)
    department = models.ForeignKey(
        Department, null=True, blank=True, on_delete=models.SET_NULL, related_name="leaders"
    )
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="leaders"
    )
    bio = models.TextField(blank=True)
    photo = SafeImageField(upload_to=RandomUploadTo("leaders"), blank=True)
    photo_alt = models.CharField(max_length=200, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    confirmation_status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.TO_BE_CONFIRMED
    )
    is_published = models.BooleanField(
        default=False, help_text="Only confirmed AND published leaders appear on the website."
    )

    objects = LeaderQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["order", "name"]

    def __str__(self) -> str:
        return f"{self.name} ({self.role_title})"
