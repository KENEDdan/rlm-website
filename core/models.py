from __future__ import annotations

from typing import Any, ClassVar

from django.core.cache import cache
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse

from .uploads import RandomUploadTo, SafeImageField

SITE_SETTINGS_CACHE_KEY = "core:site-settings:v1"

phone_validator = RegexValidator(
    r"^\+?[0-9 ()-]{6,20}$", "Enter a phone number in international format, e.g. +211 9xx xxx xxx."
)


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class PublishedQuerySet(models.QuerySet):
    def published(self) -> PublishedQuerySet:
        return self.filter(is_published=True)


class PublishableModel(TimeStampedModel):
    """User-facing content: slug, publish flag and SEO fields."""

    slug = models.SlugField(max_length=140, unique=True)
    is_published = models.BooleanField(default=False, db_index=True)
    seo_title = models.CharField(
        max_length=70, blank=True, help_text="Optional. Shown in search results (max 70 characters)."
    )
    seo_description = models.CharField(
        max_length=160, blank=True, help_text="Optional. Search result summary (max 160 characters)."
    )

    objects = PublishedQuerySet.as_manager()

    class Meta:
        abstract = True


class SingletonModel(TimeStampedModel):
    """A model with exactly one row (pk=1)."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise PermissionError("Settings cannot be deleted.")

    @classmethod
    def load(cls) -> Any:
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SiteSettings(SingletonModel):
    class Analytics(models.TextChoices):
        NONE = "none", "Disabled"
        PLAUSIBLE = "plausible", "Plausible (cookieless)"
        UMAMI = "umami", "Umami (cookieless)"

    ministry_name = models.CharField(max_length=120, default="Rebuilding Lives Ministry")
    short_name = models.CharField(max_length=20, default="RLM")
    tagline = models.CharField(max_length=160, default="Rebuilding Lives. Reviving Generations.")
    scripture_reference = models.CharField(max_length=40, default="Acts 15:16")
    scripture_text = models.TextField(
        default=(
            "After this I will return, and will build again the tabernacle of David, which is fallen "
            "down; and I will build again the ruins thereof, and I will set it up."
        ),
        help_text="Shown with the scripture reference. Choose the translation the ministry prefers.",
    )
    vision = models.TextField(blank=True)
    mission = models.TextField(blank=True)
    about_intro = models.TextField(blank=True, help_text="Short paragraph used on the home page.")
    about_body = models.TextField(
        blank=True, help_text="Full About page text. Blank lines separate paragraphs."
    )
    logo = SafeImageField(
        upload_to=RandomUploadTo("brand"), blank=True, help_text="Optional. Falls back to the built-in logo."
    )

    notification_email = models.EmailField(
        blank=True,
        help_text="Where 'new submission' alerts are sent. They never contain the submission itself.",
    )
    public_email = models.EmailField(blank=True)
    public_phone = models.CharField(max_length=30, blank=True, validators=[phone_validator])
    whatsapp_number = models.CharField(
        max_length=30,
        blank=True,
        validators=[phone_validator],
        help_text="International format. Enables the floating WhatsApp button.",
    )
    address = models.TextField(blank=True)
    footer_text = models.CharField(max_length=300, blank=True)

    analytics_provider = models.CharField(max_length=20, choices=Analytics.choices, default=Analytics.NONE)
    analytics_script_url = models.URLField(
        blank=True, help_text="e.g. https://plausible.io/js/script.js or your self-hosted Umami script."
    )
    analytics_site_id = models.CharField(
        max_length=100, blank=True, help_text="Plausible: your domain. Umami: the website ID."
    )

    retention_prayer_days = models.PositiveIntegerField(
        default=365, help_text="Delete prayer requests after this many days (0 = keep forever)."
    )
    retention_contact_days = models.PositiveIntegerField(default=365)
    retention_volunteer_days = models.PositiveIntegerField(default=730)
    retention_event_registration_days = models.PositiveIntegerField(default=365)
    retention_partnership_days = models.PositiveIntegerField(default=1095)

    class Meta:
        verbose_name = "Site settings"
        verbose_name_plural = "Site settings"

    def __str__(self) -> str:
        return "Site settings"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(SITE_SETTINGS_CACHE_KEY)

    @classmethod
    def get(cls) -> SiteSettings:
        obj = cache.get(SITE_SETTINGS_CACHE_KEY)
        if obj is None:
            obj = cls.load()
            cache.set(SITE_SETTINGS_CACHE_KEY, obj, 300)
        return obj

    @property
    def whatsapp_digits(self) -> str:
        return "".join(ch for ch in self.whatsapp_number if ch.isdigit())


class SocialLink(TimeStampedModel):
    class Platform(models.TextChoices):
        FACEBOOK = "facebook", "Facebook"
        INSTAGRAM = "instagram", "Instagram"
        TIKTOK = "tiktok", "TikTok"
        YOUTUBE = "youtube", "YouTube"
        X = "x", "X (Twitter)"
        LINKEDIN = "linkedin", "LinkedIn"
        OTHER = "other", "Other"

    platform = models.CharField(max_length=20, choices=Platform.choices)
    label = models.CharField(max_length=60, blank=True)
    url = models.URLField()
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["order", "platform"]

    def __str__(self) -> str:
        return self.label or self.get_platform_display()

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(SITE_SETTINGS_CACHE_KEY + ":social")


class Page(PublishableModel):
    """Simple editable pages such as the privacy policy and terms."""

    title = models.CharField(max_length=140)
    body = models.TextField(
        help_text="Plain text. Blank lines separate paragraphs; lines starting with '## ' are headings."
    )
    last_reviewed = models.DateField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["title"]

    def __str__(self) -> str:
        return self.title

    def get_absolute_url(self) -> str:
        return reverse("core:page", args=[self.slug])


class SubmissionStatus(models.TextChoices):
    NEW = "new", "New"
    IN_PROGRESS = "in_progress", "In progress"
    HANDLED = "handled", "Handled"
    ARCHIVED = "archived", "Archived"


class SubmissionModel(TimeStampedModel):
    """Base for anything the public submits. Personal data lives in encrypted fields on subclasses."""

    status = models.CharField(
        max_length=20, choices=SubmissionStatus.choices, default=SubmissionStatus.NEW, db_index=True
    )
    handled_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    handled_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.audit_label

    @property
    def audit_label(self) -> str:
        """Non-PII label used in audit logs, admin titles and email alerts."""
        return f"{self._meta.verbose_name} #{self.pk}"
