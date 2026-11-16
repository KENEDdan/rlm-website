from __future__ import annotations

from typing import Any, ClassVar

from django.db import models
from django.urls import reverse

from core.models import PublishableModel, TimeStampedModel
from core.uploads import RandomUploadTo, SafeFileField, SafeImageField
from media_library.models import YouTubeMixin, parse_youtube_id


class ResourceCategory(TimeStampedModel):
    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "name"]
        verbose_name_plural = "resource categories"

    def __str__(self) -> str:
        return self.name


class Series(TimeStampedModel):
    title = models.CharField(max_length=160, unique=True)
    slug = models.SlugField(max_length=160, unique=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["title"]
        verbose_name_plural = "series"

    def __str__(self) -> str:
        return self.title


class Resource(YouTubeMixin, PublishableModel):
    class Kind(models.TextChoices):
        SERMON = "sermon", "Sermon"
        DEVOTIONAL = "devotional", "Devotional"
        STUDY = "study", "Study material"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.SERMON, db_index=True)
    title = models.CharField(max_length=200)
    speaker = models.CharField(max_length=150, blank=True)
    date = models.DateField(null=True, blank=True, db_index=True)
    scripture = models.CharField(max_length=120, blank=True, help_text="e.g. Acts 15:16-17")
    summary = models.CharField(max_length=300, blank=True)
    body = models.TextField(blank=True, help_text="Notes or full text. Blank lines separate paragraphs.")
    category = models.ForeignKey(
        ResourceCategory, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    series = models.ForeignKey(
        Series, null=True, blank=True, on_delete=models.SET_NULL, related_name="resources"
    )
    audio = SafeFileField(upload_to=RandomUploadTo("audio"), kind="audio", blank=True)
    pdf = SafeFileField(upload_to=RandomUploadTo("resources"), kind="pdf", blank=True)
    thumbnail = SafeImageField(upload_to=RandomUploadTo("resources"), blank=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("resources:detail", args=[self.slug])

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = parse_youtube_id(self.youtube_url)
        super().save(*args, **kwargs)
