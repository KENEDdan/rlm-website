from __future__ import annotations

from typing import Any, ClassVar

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .uploads import RandomUploadTo, SafeImageField
from .validators import SAFE_LINK_HELP, is_safe_link, validate_safe_link

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
        upload_to=RandomUploadTo("brand"),
        blank=True,
        help_text="Logo for LIGHT backgrounds (site header). PNG with transparency works best. "
        "Leave empty to use the built-in logo.",
    )
    logo_on_dark = SafeImageField(
        upload_to=RandomUploadTo("brand"),
        blank=True,
        help_text="Logo for DARK backgrounds (footer, home page hero, link previews). Leave empty for the built-in one.",
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
    def analytics_enabled(self) -> bool:
        """Analytics only load (after consent) when a provider, script and site id are all set."""
        return self.analytics_provider != "none" and bool(
            self.analytics_script_url and self.analytics_site_id
        )

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
    show_in_footer = models.BooleanField(
        default=False, help_text="List this page in the website footer (e.g. 'Statement of faith')."
    )
    order = models.PositiveSmallIntegerField(default=0, help_text="Footer position (lower first).")

    class Meta:
        ordering: ClassVar = ["order", "title"]

    def __str__(self) -> str:
        return self.title

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(SITE_SETTINGS_CACHE_KEY + ":footer-pages")

    def get_absolute_url(self) -> str:
        if self.slug in ("privacy", "terms"):
            return reverse(f"core:{self.slug}")
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


SITE_TEXT_CACHE_KEY = "core:site-text:v1"


class PageText(TimeStampedModel):
    """Editable wording for a page header or home/shared section (one row per place on the site).

    Rows are created from ``core.page_texts.PAGE_TEXT_DEFAULTS`` on migrate; staff can edit but not add or
    delete them, because each key is wired into a template.
    """

    key = models.SlugField(max_length=60, unique=True, editable=False)
    label = models.CharField(max_length=120, editable=False, help_text="Where this text appears.")
    eyebrow = models.CharField(
        max_length=60, blank=True, help_text="Small label above the heading (optional)."
    )
    heading = models.CharField(max_length=160)
    highlight = models.CharField(
        max_length=160, blank=True, help_text="Optional second line in the flame colours (home hero only)."
    )
    intro = models.TextField(max_length=400, blank=True, help_text="Short text under the heading (optional).")
    seo_title = models.CharField(
        max_length=70, blank=True, help_text="Optional. Browser tab / search result title for this page."
    )
    seo_description = models.CharField(
        max_length=160, blank=True, help_text="Optional. Search result summary for this page."
    )

    class Meta:
        ordering: ClassVar = ["label"]
        verbose_name = "page text"
        verbose_name_plural = "page text"

    def __str__(self) -> str:
        return self.label

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(SITE_TEXT_CACHE_KEY + ":pages")


class FormOption(TimeStampedModel):
    """One choice in a public form list (e.g. a volunteer area of service), managed in the admin.

    The stored ``value`` never changes once used (old submissions keep pointing at it); the ``label`` can be
    renamed. Options are switched off instead of deleted so old submissions still show a readable label.
    """

    class List(models.TextChoices):
        VOLUNTEER_INTEREST = "volunteer_interest", "Volunteer form: where would you like to serve?"
        VOLUNTEER_AVAILABILITY = "volunteer_availability", "Volunteer form: availability"
        CONTACT_TOPIC = "contact_topic", "Contact form: topic"
        PARTNER_TYPE = "partner_type", "Partnership form: I am partnering as"
        PARTNER_INTEREST = "partner_interest", "Partnership form: main interest"

    list = models.CharField(max_length=40, choices=List.choices, db_index=True)
    value = models.SlugField(
        max_length=20,
        help_text="Short internal code (lowercase, no spaces), e.g. 'prison-ministry'. Cannot be changed later.",
    )
    label = models.CharField(max_length=120, help_text="What visitors see.")
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(
        default=True, help_text="Untick to hide it from the form (old answers keep it)."
    )

    class Meta:
        ordering: ClassVar = ["list", "order", "label"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["list", "value"], name="unique_option_per_list")
        ]
        verbose_name = "form option"

    def __str__(self) -> str:
        return f"{self.get_list_display()}: {self.label}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(f"{SITE_TEXT_CACHE_KEY}:options:{self.list}")

    def clean(self) -> None:
        from django.core.exceptions import ValidationError

        if not self.is_active and self.list:
            others = FormOption.objects.filter(list=self.list, is_active=True).exclude(pk=self.pk)
            if not others.exists():
                raise ValidationError(
                    "At least one option in this list must stay active, or the form cannot be sent."
                )


# ---------------------------------------------------------------- home page sliders
HERO_SLIDE_LIMIT = 5


class HeroSlideQuerySet(models.QuerySet):
    def live(self, now: Any = None) -> HeroSlideQuerySet:
        """Switched on, and inside the optional start/end window."""
        now = now or timezone.now()
        return self.filter(
            Q(is_active=True),
            Q(start_at__isnull=True) | Q(start_at__lte=now),
            Q(end_at__isnull=True) | Q(end_at__gt=now),
        )


class HeroSlide(TimeStampedModel):
    """One slide of the home page hero slider (managed by Media & Communications and the Founder)."""

    title = models.CharField(max_length=120, help_text="Large heading. Keep it short (under 60 characters).")
    subtitle = models.TextField(
        max_length=300, blank=True, help_text="One or two sentences under the heading (optional)."
    )
    image = SafeImageField(
        upload_to=RandomUploadTo("hero"),
        blank=True,
        help_text="Landscape photo, ideally 1920 x 900 pixels (JPG, PNG or WebP, max size as for all "
        "uploads). A dark shade is added automatically so the text stays readable. Leave empty for the "
        "dark flame background with the logo.",
    )
    image_alt = models.CharField(
        max_length=200,
        blank=True,
        help_text="Describe the photo for people using screen readers. Leave empty if it is only decoration.",
    )
    button_text = models.CharField(
        max_length=40,
        blank=True,
        help_text="e.g. Give, Volunteer, Register, Watch. Leave empty for no button.",
    )
    button_link = models.CharField(
        max_length=300, blank=True, validators=[validate_safe_link], help_text=SAFE_LINK_HELP
    )
    show_scripture = models.BooleanField(
        default=False, help_text="Show the scripture from Site settings (Acts 15:16) under the text."
    )
    order = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers show first.")
    is_active = models.BooleanField(default=True, help_text="Untick to hide the slide without deleting it.")
    start_at = models.DateTimeField(
        null=True, blank=True, help_text="Optional: do not show before this date and time."
    )
    end_at = models.DateTimeField(
        null=True, blank=True, help_text="Optional: stop showing after this date and time."
    )

    objects = HeroSlideQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["order", "pk"]
        verbose_name = "hero slide"

    def __str__(self) -> str:
        return self.title

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            errors["end_at"] = "The end must be after the start."
        if self.button_text and not self.button_link:
            errors["button_link"] = "Add the page the button should open."
        if self.button_link and not self.button_text:
            errors["button_text"] = "Add the words shown on the button."
        if errors:
            raise ValidationError(errors)

    @property
    def safe_button_link(self) -> str:
        """The button link, re-checked at display time (defence in depth against rows saved outside forms)."""
        return self.button_link if is_safe_link(self.button_link) else ""

    @property
    def status(self) -> str:
        now = timezone.now()
        if not self.is_active:
            return "Switched off"
        if self.start_at and self.start_at > now:
            return "Scheduled"
        if self.end_at and self.end_at <= now:
            return "Ended"
        return "Showing"


class Partner(TimeStampedModel):
    """A partner or supporter shown in the logo strip on the home page (only when published)."""

    name = models.CharField(max_length=120, help_text="Used as the logo's text alternative.")
    logo = SafeImageField(
        upload_to=RandomUploadTo("partners"),
        help_text="PNG with a transparent background works best, at least 400 pixels wide.",
    )
    website = models.CharField(
        max_length=300,
        blank=True,
        validators=[validate_safe_link],
        help_text="Optional. Must start with https://",
    )
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(
        default=False, help_text="Only publish with the partner's permission to show their logo."
    )

    objects = PublishedQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["order", "name"]

    def __str__(self) -> str:
        return self.name

    @property
    def safe_website(self) -> str:
        return self.website if is_safe_link(self.website) else ""
