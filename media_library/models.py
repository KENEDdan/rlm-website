from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from core.models import PublishableModel, TimeStampedModel
from core.uploads import RandomUploadTo, SafeFileField, SafeImageField

YOUTUBE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
YOUTUBE_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "youtu.be", "www.youtube-nocookie.com"}


def parse_youtube_id(value: str) -> str:
    """Accept a YouTube URL or bare ID and return the 11-character video ID (or raise)."""
    value = (value or "").strip()
    if YOUTUBE_ID_RE.match(value):
        return value
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or parsed.hostname not in YOUTUBE_HOSTS:
        raise ValidationError("Enter a YouTube link (youtube.com or youtu.be) or an 11-character video ID.")
    candidate = ""
    if parsed.hostname == "youtu.be":
        candidate = parsed.path.lstrip("/").split("/")[0]
    elif parsed.path == "/watch":
        candidate = parse_qs(parsed.query).get("v", [""])[0]
    else:
        parts = [p for p in parsed.path.split("/") if p]
        if len(parts) >= 2 and parts[0] in {"embed", "shorts", "live", "v"}:
            candidate = parts[1]
    if not YOUTUBE_ID_RE.match(candidate):
        raise ValidationError("Could not find a valid YouTube video ID in that link.")
    return candidate


class YouTubeMixin(models.Model):
    youtube_url = models.CharField(
        max_length=200, blank=True, help_text="Paste the YouTube link. Videos play via youtube-nocookie.com."
    )
    youtube_id = models.CharField(max_length=11, blank=True, editable=False)

    class Meta:
        abstract = True

    def clean(self) -> None:
        super().clean()
        if self.youtube_url:
            try:
                self.youtube_id = parse_youtube_id(self.youtube_url)
            except ValidationError as exc:
                raise ValidationError({"youtube_url": exc.messages}) from exc
        else:
            self.youtube_id = ""


class Album(PublishableModel):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    date = models.DateField(null=True, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="albums"
    )
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="albums"
    )
    cover = SafeImageField(upload_to=RandomUploadTo("albums"), blank=True)
    cover_alt = models.CharField(max_length=200, blank=True)

    class Meta:
        ordering: ClassVar = ["-date", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("media_library:album", args=[self.slug])

    @property
    def cover_image(self):  # type: ignore[no-untyped-def]
        if self.cover:
            return self.cover
        first = self.photos.filter(is_published=True).first()
        return first.image if first else None


class Photo(TimeStampedModel):
    album = models.ForeignKey(Album, on_delete=models.CASCADE, related_name="photos")
    image = SafeImageField(upload_to=RandomUploadTo("photos"))
    alt_text = models.CharField(
        max_length=200, help_text="Describe the photo for people using screen readers."
    )
    caption = models.CharField(max_length=300, blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["order", "created_at"]

    def __str__(self) -> str:
        return self.alt_text or f"Photo #{self.pk}"


class Video(YouTubeMixin, PublishableModel):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    album = models.ForeignKey(Album, null=True, blank=True, on_delete=models.SET_NULL, related_name="videos")
    recorded_on = models.DateField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-recorded_on", "-created_at"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args, **kwargs) -> None:  # type: ignore[no-untyped-def]
        if self.youtube_url and not self.youtube_id:
            self.youtube_id = parse_youtube_id(self.youtube_url)
        super().save(*args, **kwargs)


class Report(PublishableModel):
    title = models.CharField(max_length=160)
    summary = models.TextField(blank=True)
    year = models.PositiveSmallIntegerField(null=True, blank=True)
    file = SafeFileField(upload_to=RandomUploadTo("reports"), kind="pdf")

    class Meta:
        ordering: ClassVar = ["-year", "-created_at"]

    def __str__(self) -> str:
        return self.title


class Testimony(PublishableModel):
    title = models.CharField(max_length=160)
    person_display_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="Only publish a name with the person's written consent. Leave blank for 'Anonymous'.",
    )
    consent_confirmed = models.BooleanField(
        default=False, help_text="Tick only when the person has agreed to their testimony being published."
    )
    body = models.TextField()
    photo = SafeImageField(upload_to=RandomUploadTo("testimonies"), blank=True)
    photo_alt = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="testimonies"
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name_plural = "testimonies"

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        if self.is_published and not self.consent_confirmed:
            raise ValidationError({"consent_confirmed": "Confirm consent before publishing a testimony."})
