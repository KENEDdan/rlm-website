from __future__ import annotations

from typing import Any, ClassVar

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import Q
from django.urls import reverse
from django.utils import timezone

from .uploads import RandomUploadTo, SafeFileField, SafeImageField
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
    """SYSTEM settings (Super Admin only): staff alerts, analytics, retention, approval rules.

    Everything visitors see (name, logos, vision, mission, contacts, footer) is in ``SiteContent``, which the
    Technical Team edits. Bank and payment details are in ``giving.GivingSettings`` (Finance only). Three
    models, so each role's access is structural (Django permissions per model), not hidden form fields.
    """

    class Analytics(models.TextChoices):
        NONE = "none", "Disabled"
        PLAUSIBLE = "plausible", "Plausible (cookieless)"
        UMAMI = "umami", "Umami (cookieless)"

    notification_email = models.EmailField(
        blank=True,
        help_text="Where 'new submission' alerts are sent. They never contain the submission itself.",
    )
    vision_mission_approval_required = models.BooleanField(
        default=True,
        help_text="Changes to the Vision and Mission need a draft, preview and approval by the Super Admin or "
        "Executive Director before they are published.",
    )

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
    retention_unsuccessful_days = models.PositiveIntegerField(
        default=365,
        help_text="Delete membership, discipleship, partnership and finance-volunteer applications that were NOT "
        "successful this many days after the decision, keeping only anonymous statistics (0 = keep forever).",
    )
    retention_unsuccessful_minor_days = models.PositiveIntegerField(
        default=90,
        help_text="The same for applicants under 18 (never longer than the period above).",
    )
    retention_notice_days = models.PositiveIntegerField(
        default=30, help_text="Applications deleted within this many days are listed in the monthly report."
    )

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


SITE_CONTENT_CACHE_KEY = "core:site-content:v1"
VISION_MISSION_FIELDS = ("vision", "mission")


class SiteContent(SingletonModel):
    """What visitors see across the site: identity, logos, Vision and Mission, public contacts, footer.

    Managed by the Technical Team (Website Administration) and the Super Admin. Vision and Mission are the
    single source of truth for the About page, home page, footer and default meta description; while
    ``SiteSettings.vision_mission_approval_required`` is on they change only through ``ContentChangeRequest``.
    """

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
    # Not editable in any form: changed only through ContentChangeRequest (draft -> preview -> approval ->
    # publish, with version history and rollback). Seeded verbatim by migration core 0015.
    vision = models.TextField(blank=True, editable=False)
    mission = models.TextField(blank=True, editable=False)
    about_intro = models.TextField(blank=True, help_text="Short paragraph used on the home page.")
    about_body = models.TextField(
        blank=True, help_text="Full About page text. Blank lines separate paragraphs."
    )
    logo = SafeImageField(
        upload_to=RandomUploadTo("brand"),
        policy="logo",
        blank=True,
        help_text="Logo for LIGHT backgrounds (site header). PNG with transparency works best. "
        "Leave empty to use the built-in logo.",
    )
    logo_on_dark = SafeImageField(
        upload_to=RandomUploadTo("brand"),
        policy="logo",
        blank=True,
        help_text="Logo for DARK backgrounds (footer, home page hero, link previews). Leave empty for the built-in one.",
    )

    favicon = SafeImageField(
        upload_to=RandomUploadTo("brand"),
        policy="favicon",
        blank=True,
        help_text="Square PNG, at least 512 x 512 pixels. Leave empty for the built-in icon.",
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

    vision_mission_updated_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        verbose_name = "site content"
        verbose_name_plural = "site content"

    def __str__(self) -> str:
        return "Site content"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        cache.delete(SITE_CONTENT_CACHE_KEY)

    @classmethod
    def get(cls) -> SiteContent:
        obj = cache.get(SITE_CONTENT_CACHE_KEY)
        if obj is None:
            obj = cls.load()
            cache.set(SITE_CONTENT_CACHE_KEY, obj, 300)
        return obj

    @property
    def whatsapp_digits(self) -> str:
        return "".join(ch for ch in self.whatsapp_number if ch.isdigit())

    @property
    def meta_description(self) -> str:
        """Default meta description: the Mission (single source), cut at a word to fit 158 characters."""
        text = " ".join(self.mission.split())
        if len(text) <= 158:
            return text
        return text[:155].rsplit(" ", 1)[0] + "..."


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


class RetainedApplication(models.Model):
    """Lifecycle and retention fields shared by the four application forms (ministry decision 8).

    ``outcome_at`` starts the retention clock. An unsuccessful application is deleted (keeping only an anonymous
    statistic) after ``SiteSettings.retention_unsuccessful_days`` (minors: ``retention_unsuccessful_minor_days``)
    unless it is on legal hold. A successful one is converted into the proper ministry record and keeps only
    ``record_reference``.
    """

    class Outcome(models.TextChoices):
        PENDING = "pending", "Pending"
        SUCCESSFUL = "successful", "Approved (successful)"
        UNSUCCESSFUL = "unsuccessful", "Unsuccessful"

    outcome = models.CharField(
        max_length=12, choices=Outcome.choices, default=Outcome.PENDING, db_index=True, editable=False
    )
    outcome_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    legal_hold = models.BooleanField(
        default=False, editable=False, help_text="Pauses automatic deletion (set by the Super Admin)."
    )
    legal_hold_reason = models.CharField(max_length=300, blank=True, editable=False)
    record_reference = models.CharField(
        max_length=80, blank=True, editable=False, help_text="Where a successful application now lives."
    )

    class Meta:
        abstract = True


class ApplicationStat(models.Model):
    """Anonymous counts kept after applications are converted or deleted: type, branch, month, outcome only."""

    kind = models.CharField(max_length=30, db_index=True)
    branch = models.ForeignKey(
        "branches.Branch", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    month = models.DateField(help_text="First day of the month the application was received.")
    outcome = models.CharField(max_length=12, choices=RetainedApplication.Outcome.choices)
    count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["-month", "kind"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["kind", "branch", "month", "outcome"],
                name="unique_application_stat",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.kind} {self.month:%b %Y} {self.outcome}: {self.count}"


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
        PARTNER_TYPE = "partner_type", "Partnership form: partnership category"
        PARTNER_INTEREST = "partner_interest", "Partnership form (old): main interest"
        PARTNER_AREA = "partner_area", "Partnership form: areas to partner in"
        PARTNERSHIP_TYPE = "partnership_type", "Partnership form: preferred type of partnership"

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


class HeroContent(TimeStampedModel):
    """Wording and background shared by the home page hero (``HeroSettings``) and each slider slide.

    Background: "Theme colour" (default; brand black with the flame gradient), "Photo" or "Video". Whatever is
    chosen, a missing photo, video or poster falls back cleanly to the theme colour (``effective_background``).
    """

    class Background(models.TextChoices):
        THEME = "theme", "Theme colour (brand black with the flame accent)"
        PHOTO = "photo", "Photo"
        VIDEO = "video", "Video (short silent loop)"

    class Align(models.TextChoices):
        LEFT = "left", "Left"
        CENTER = "center", "Centre"

    class Tone(models.TextChoices):
        LIGHT = "light", "Light text (for dark backgrounds)"
        DARK = "dark", "Dark text (for light backgrounds)"

    title = models.CharField(
        "headline", max_length=120, help_text="Large heading. Keep it short (under 60 characters)."
    )
    subtitle = models.TextField(
        "sub-headline",
        max_length=300,
        blank=True,
        help_text="One or two sentences under the heading (optional).",
    )
    background_type = models.CharField(max_length=10, choices=Background.choices, default=Background.THEME)
    image = SafeImageField(
        "background photo",
        upload_to=RandomUploadTo("hero"),
        policy="hero_photo",
        blank=True,
        help_text="Landscape photo, at least 1600 pixels wide (ideally 1920 x 900). JPEG, PNG or WebP, max 5 MB. "
        "Location data is removed automatically.",
    )
    image_alt = models.CharField(
        max_length=200,
        blank=True,
        help_text="Describe the photo for people using screen readers. Leave empty if it is only decoration.",
    )
    focal_x = models.PositiveSmallIntegerField(
        "focal point across (%)",
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="Which part of the photo stays visible on narrow screens: 0 = left edge, 100 = right edge.",
    )
    focal_y = models.PositiveSmallIntegerField(
        "focal point down (%)",
        default=50,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        help_text="0 = top edge, 100 = bottom edge.",
    )
    overlay_opacity = models.PositiveSmallIntegerField(
        "dark overlay (%)",
        default=45,
        validators=[MinValueValidator(0), MaxValueValidator(80)],
        help_text="0 to 80. A darker overlay keeps light text readable on bright photos.",
    )
    video = SafeFileField(
        "background video",
        upload_to=RandomUploadTo("hero-video"),
        policy="hero_video",
        blank=True,
        help_text="MP4 (H.264) or WebM, max 15 MB and 15 seconds, no sound. Recommended: a loop of 10 seconds or "
        "less, 1080p, under 10 MB. Visitors who prefer reduced motion, use data saver or a slow connection see "
        "the poster instead.",
    )
    video_poster = SafeImageField(
        "video poster image",
        upload_to=RandomUploadTo("hero"),
        policy="hero_photo",
        blank=True,
        help_text="REQUIRED with a video: shown before the video loads and instead of it on slow connections.",
    )
    text_align = models.CharField(max_length=10, choices=Align.choices, default=Align.LEFT)
    text_tone = models.CharField("text colour", max_length=10, choices=Tone.choices, default=Tone.LIGHT)
    button_text = models.CharField(
        "button 1 label",
        max_length=40,
        blank=True,
        help_text="e.g. Give, Volunteer, Register, Watch. Leave empty for no button.",
    )
    button_link = models.CharField(
        "button 1 link", max_length=300, blank=True, validators=[validate_safe_link], help_text=SAFE_LINK_HELP
    )
    button2_text = models.CharField("button 2 label", max_length=40, blank=True)
    button2_link = models.CharField(
        "button 2 link", max_length=300, blank=True, validators=[validate_safe_link], help_text=SAFE_LINK_HELP
    )
    show_scripture = models.BooleanField(
        default=False, help_text="Show the scripture from Site content (Acts 15:16) under the text."
    )
    # Brightest-area luminance (0-1) of the photo / poster, measured when it is uploaded (contrast check).
    image_luminance = models.FloatField(null=True, blank=True, editable=False)
    poster_luminance = models.FloatField(null=True, blank=True, editable=False)

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .hero import measure_luminance

        # A photo or video just uploaded while the type is still "Theme colour" is meant to be shown.
        if self.background_type == self.Background.THEME:
            if self.video and not self.video._committed:
                self.background_type = self.Background.VIDEO
            elif self.image and not self.image._committed:
                self.background_type = self.Background.PHOTO
        for field, target in (("image", "image_luminance"), ("video_poster", "poster_luminance")):
            file = getattr(self, field)
            if not file:
                setattr(self, target, None)
            elif not file._committed or getattr(self, target) is None:
                setattr(self, target, measure_luminance(file))
        super().save(*args, **kwargs)

    def clean(self) -> None:
        super().clean()
        errors: dict[str, str] = {}
        for text, link, n in (("button_text", "button_link", "1"), ("button2_text", "button2_link", "2")):
            if getattr(self, text) and not getattr(self, link):
                errors[link] = f"Add the page button {n} should open."
            if getattr(self, link) and not getattr(self, text):
                errors[text] = f"Add the words shown on button {n}."
        if self.video and not self.video_poster:
            errors["video_poster"] = "A poster image is required with a background video."
        if errors:
            raise ValidationError(errors)

    # ------------------------------------------------------------------ display helpers
    @property
    def effective_background(self) -> str:
        """What visitors actually get: a chosen photo/video only when its files exist, else the theme colour."""
        if self.background_type == self.Background.PHOTO and self.image:
            return "photo"
        if self.background_type == self.Background.VIDEO and self.video and self.video_poster:
            return "video"
        return "theme"

    @property
    def background_image(self) -> Any:
        """The image behind the text: the photo, or the video's poster."""
        return {"photo": self.image, "video": self.video_poster}.get(self.effective_background)

    @property
    def background_luminance(self) -> float | None:
        return {"photo": self.image_luminance, "video": self.poster_luminance}.get(self.effective_background)

    @property
    def contrast_ratio(self) -> float:
        from .hero import contrast_ratio

        return contrast_ratio(
            self.effective_background, self.background_luminance, self.overlay_opacity, self.text_tone
        )

    @property
    def contrast_ok(self) -> bool:
        from .hero import AA_NORMAL

        return self.contrast_ratio >= AA_NORMAL

    @property
    def safe_button_link(self) -> str:
        """The button link, re-checked at display time (defence in depth against rows saved outside forms)."""
        return self.button_link if is_safe_link(self.button_link) else ""

    @property
    def safe_button2_link(self) -> str:
        return self.button2_link if is_safe_link(self.button2_link) else ""

    @property
    def buttons(self) -> list[tuple[str, str]]:
        out = []
        if self.button_text and self.safe_button_link:
            out.append((self.button_text, self.safe_button_link))
        if self.button2_text and self.safe_button2_link:
            out.append((self.button2_text, self.safe_button2_link))
        return out

    @property
    def dom_id(self) -> str:
        return f"hero-{self._meta.model_name}-{self.pk or 'new'}"

    @property
    def video_mime(self) -> str:
        return "video/webm" if self.video and self.video.name.lower().endswith(".webm") else "video/mp4"

    @property
    def object_position(self) -> str:
        return f"{self.focal_x}% {self.focal_y}%"

    @property
    def overlay_alpha(self) -> str:
        return f"{self.overlay_opacity / 100:.2f}"


class HeroSlide(HeroContent):
    """One slide of the home page hero slider (Technical Team, Media & Communications and the Founder)."""

    order = models.PositiveSmallIntegerField(default=0, help_text="Lower numbers show first.")
    is_active = models.BooleanField(
        default=True, help_text="Untick to hide the slide without deleting it (preview it first)."
    )
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
        if self.start_at and self.end_at and self.end_at <= self.start_at:
            raise ValidationError({"end_at": "The end must be after the start."})

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


class HeroSettings(HeroContent):
    """The home page hero shown when no slider slides are live. Two rows: the DRAFT the Technical Team edits and
    previews, and the LIVE one visitors see. Publishing copies the draft to live (versioned, so the previous live
    hero can be restored with "Revert to previous")."""

    class State(models.TextChoices):
        DRAFT = "draft", "Draft"
        LIVE = "live", "Live"

    state = models.CharField(max_length=5, choices=State.choices, unique=True, editable=False)
    published_at = models.DateTimeField(null=True, blank=True, editable=False)
    published_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    COPY_FIELDS = (
        "title", "subtitle", "background_type", "image", "image_alt", "focal_x", "focal_y", "overlay_opacity",
        "video", "video_poster", "text_align", "text_tone", "button_text", "button_link", "button2_text",
        "button2_link", "show_scripture", "image_luminance", "poster_luminance",
    )  # fmt: skip

    class Meta:
        verbose_name = "hero settings"
        verbose_name_plural = "hero settings"

    def __str__(self) -> str:
        return f"Home hero ({self.get_state_display().lower()})"

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise PermissionError("The hero settings cannot be deleted.")

    @classmethod
    def get(cls, state: str) -> HeroSettings:
        obj = cls.objects.filter(state=state).first()
        if obj is None:
            live = cls.objects.filter(state=cls.State.LIVE).first()
            obj = cls(state=state, title="Rebuilding Lives. Reviving Generations.")
            if live is not None:
                obj.copy_from(live)
            obj.save()
        return obj

    @classmethod
    def live(cls) -> HeroSettings:
        return cls.get(cls.State.LIVE)

    @classmethod
    def draft(cls) -> HeroSettings:
        return cls.get(cls.State.DRAFT)

    def copy_from(self, other: HeroContent) -> None:
        for name in self.COPY_FIELDS:
            setattr(self, name, getattr(other, name))

    def differs_from(self, other: HeroContent) -> bool:
        def value(obj: Any, name: str) -> Any:
            v = getattr(obj, name)
            return v.name if hasattr(v, "name") and not isinstance(v, str) else v

        return any(value(self, n) != value(other, n) for n in self.COPY_FIELDS)


class Partner(TimeStampedModel):
    """A partner or supporter shown in the logo strip on the home page (only when published)."""

    name = models.CharField(max_length=120, help_text="Used as the logo's text alternative.")
    logo = SafeImageField(
        upload_to=RandomUploadTo("partners"),
        policy="content_image",
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


class UploadLimit(TimeStampedModel):
    """Super Admin adjustment of one upload policy's limits (formats stay fixed in core/upload_policy.py).

    Empty values keep the built-in default. Sizes can never exceed the web server's request cap.
    """

    policy = models.CharField(max_length=30, unique=True)
    max_mb = models.DecimalField("maximum size (MB)", max_digits=5, decimal_places=1, null=True, blank=True)
    min_width = models.PositiveIntegerField(
        "minimum width (pixels)", null=True, blank=True, help_text="Images only. 0 = no minimum."
    )
    max_seconds = models.PositiveSmallIntegerField(
        "maximum length (seconds)", null=True, blank=True, help_text="Background video only (at most 30)."
    )

    class Meta:
        ordering: ClassVar = ["policy"]
        verbose_name = "upload limit"

    def __str__(self) -> str:
        from .upload_policy import POLICIES

        policy = POLICIES.get(self.policy)
        return policy.label if policy else self.policy

    def save(self, *args: Any, **kwargs: Any) -> None:
        from .upload_policy import POLICY_CACHE_KEY

        super().save(*args, **kwargs)
        cache.delete(POLICY_CACHE_KEY)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        from .upload_policy import POLICY_CACHE_KEY

        result = super().delete(*args, **kwargs)
        cache.delete(POLICY_CACHE_KEY)
        return result

    def clean(self) -> None:
        from .upload_policy import HARD_MAX_BYTES, HARD_MAX_VIDEO_SECONDS, MB, POLICIES

        errors: dict[str, str] = {}
        policy = POLICIES.get(self.policy)
        if policy is None:
            errors["policy"] = "Unknown upload policy."
        if self.max_mb is not None and not (0 < self.max_mb * MB <= HARD_MAX_BYTES):
            errors["max_mb"] = f"Choose between 0.1 and {HARD_MAX_BYTES // MB} MB."
        if self.max_seconds is not None and policy and not policy.max_seconds:
            errors["max_seconds"] = "Only the background video has a length limit."
        if self.max_seconds is not None and not (1 <= self.max_seconds <= HARD_MAX_VIDEO_SECONDS):
            errors["max_seconds"] = f"Choose between 1 and {HARD_MAX_VIDEO_SECONDS} seconds."
        if self.min_width is not None and policy and not ({"image"} & policy.kinds):
            errors["min_width"] = "Only image policies have a minimum width."
        if errors:
            raise ValidationError(errors)


# ---------------------------------------------------------------------------------------------- website versions
class AppendOnlyModel(models.Model):
    """Rows are written once: no updates (after creation) and no deletes, even from the admin."""

    class Meta:
        abstract = True

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and not getattr(self, "_allow_update", False):
            raise PermissionError(f"{type(self).__name__} rows cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> Any:
        raise PermissionError(f"{type(self).__name__} rows cannot be deleted.")


class ContentVersion(AppendOnlyModel):
    """A snapshot of a website-content record after every change (who, when, what), for rollback.

    Written by ``core.versioning`` for every Technical Team model, in the admin and the portal.
    """

    class Action(models.TextChoices):
        ADD = "add", "Added"
        CHANGE = "change", "Changed"
        DELETE = "delete", "Deleted"
        PUBLISH = "publish", "Published"
        ROLLBACK = "rollback", "Rolled back"

    content_type = models.ForeignKey("contenttypes.ContentType", on_delete=models.PROTECT, related_name="+")
    object_id = models.CharField(max_length=40, db_index=True)
    object_repr = models.CharField(max_length=200)
    action = models.CharField(max_length=10, choices=Action.choices)
    data = models.JSONField(help_text="Field values after the change (files as stored names).")
    changed_fields = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    created_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    note = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at", "-pk"]
        indexes: ClassVar = [models.Index(fields=["content_type", "object_id", "-created_at"])]
        verbose_name = "content version"

    def __str__(self) -> str:
        return f"{self.object_repr}: {self.get_action_display()} {self.created_at:%d %b %Y %H:%M}"

    @property
    def model_label(self) -> str:
        return f"{self.content_type.app_label}.{self.content_type.model}"


class ContentChangeRequest(TimeStampedModel):
    """A proposed new Vision or Mission: draft -> preview -> (approval) -> publish. Published rows are the
    version history; rolling back proposes an earlier published text again."""

    class Field(models.TextChoices):
        VISION = "vision", "Vision"
        MISSION = "mission", "Mission"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Waiting for approval"
        APPROVED = "approved", "Approved, ready to publish"
        REJECTED = "rejected", "Not approved"
        PUBLISHED = "published", "Published"
        WITHDRAWN = "withdrawn", "Withdrawn"
        SUPERSEDED = "superseded", "Replaced by a later change"

    field = models.CharField(max_length=10, choices=Field.choices)
    text = models.TextField(max_length=2000)
    previous_text = models.TextField(blank=True, editable=False)
    reason = models.CharField(max_length=300, blank=True, help_text="Why the wording should change.")
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT, db_index=True)
    rollback_of = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="+", editable=False
    )
    created_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    decided_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)
    decision_note = models.CharField(max_length=300, blank=True, editable=False)
    published_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    published_at = models.DateTimeField(null=True, blank=True, editable=False, db_index=True)
    approval_was_required = models.BooleanField(default=True, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name = "vision/mission change"

    def __str__(self) -> str:
        return f"{self.get_field_display()} change #{self.pk} ({self.get_status_display()})"

    @property
    def audit_label(self) -> str:
        return f"{self.field} change #{self.pk}"


class BackupRun(models.Model):
    """One nightly backup result, written by docker/backup/backup.sh (shown on the Website dashboard)."""

    finished_at = models.DateTimeField(db_index=True)
    ok = models.BooleanField()
    detail = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["-finished_at"]
        get_latest_by = "finished_at"

    def __str__(self) -> str:
        return f"Backup {'OK' if self.ok else 'FAILED'} {self.finished_at:%d %b %Y %H:%M}"
