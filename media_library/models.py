from __future__ import annotations

import re
from typing import ClassVar
from urllib.parse import parse_qs, urlparse

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from core.models import PublishableModel, PublishedQuerySet, TimeStampedModel
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
    cover = SafeImageField(upload_to=RandomUploadTo("albums"), policy="gallery_photo", blank=True)
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
    image = SafeImageField(upload_to=RandomUploadTo("photos"), policy="gallery_photo")
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
    file = SafeFileField(upload_to=RandomUploadTo("reports"), policy="public_document")

    class Meta:
        ordering: ClassVar = ["-year", "-created_at"]

    def __str__(self) -> str:
        return self.title


class TestimonyQuerySet(PublishedQuerySet):
    def approved(self) -> TestimonyQuerySet:
        """What the public may see: published, consent recorded AND approved by staff."""
        return self.filter(is_published=True, consent_confirmed=True, is_approved=True, subject_is_adult=True)


class Testimony(PublishableModel):
    class NameDisplay(models.TextChoices):
        ANONYMOUS = "anonymous", "Anonymous (no name)"
        INITIALS = "initials", "Initials only, e.g. M. K."
        FIRST_NAME = "first", "First name only"
        FULL_NAME = "full", "Full name (needs the person's explicit consent below)"

    title = models.CharField(max_length=160)
    person_display_name = models.CharField(
        max_length=120,
        blank=True,
        help_text="The person's name. The website only shows what 'Name shown' allows.",
    )
    name_display = models.CharField(
        "name shown",
        max_length=10,
        choices=NameDisplay.choices,
        default=NameDisplay.INITIALS,
        help_text="Without explicit consent only initials or the first name are ever shown.",
    )
    full_name_consent = models.BooleanField(
        "consent to show full name",
        default=False,
        help_text="Tick only when the person has explicitly agreed (in writing) to their full name being shown.",
    )
    consent_confirmed = models.BooleanField(
        default=False, help_text="Tick only when the person has agreed to their testimony being published."
    )
    subject_is_adult = models.BooleanField(
        "the person is 18 or over",
        default=False,
        help_text="Required before approval: testimonies of children are never published (privacy rule for minors).",
    )
    is_approved = models.BooleanField(
        "approved",
        default=False,
        help_text="Reviewed and approved for the website (home page slider and Testimonies page).",
    )
    body = models.TextField()
    photo = SafeImageField(upload_to=RandomUploadTo("testimonies"), policy="content_image", blank=True)
    photo_alt = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="testimonies"
    )

    objects = TestimonyQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name_plural = "testimonies"

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        errors: dict[str, str] = {}
        if self.is_published and not self.consent_confirmed:
            errors["consent_confirmed"] = "Confirm consent before publishing a testimony."
        if self.is_approved and not self.consent_confirmed:
            errors["is_approved"] = "A testimony can only be approved once consent is confirmed."
        if (self.is_approved or self.is_published) and not self.subject_is_adult:
            errors["subject_is_adult"] = (
                "Testimonies of children (under 18) are never published. Confirm the person is 18 or over."
            )
        if self.name_display == self.NameDisplay.FULL_NAME and not self.full_name_consent:
            errors["full_name_consent"] = (
                "The full name can only be shown with the person's explicit consent. "
                "Choose first name or initials instead."
            )
        if errors:
            raise ValidationError(errors)

    @property
    def public_name(self) -> str:
        """The only form of the name that may appear on the website."""
        parts = self.person_display_name.split()
        mode = self.name_display
        if not parts or mode == self.NameDisplay.ANONYMOUS:
            return "Anonymous"
        if mode == self.NameDisplay.FULL_NAME and self.full_name_consent:
            return " ".join(parts)
        if mode == self.NameDisplay.INITIALS:
            return " ".join(f"{p[0].upper()}." for p in parts[:3])
        return parts[0]  # first name only (also the fallback when full-name consent is missing)
