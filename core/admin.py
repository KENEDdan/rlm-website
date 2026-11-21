from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse, HttpResponseRedirect
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from .admin_mixins import AuditedAdminMixin
from .models import (
    HERO_SLIDE_LIMIT,
    FormOption,
    HeroSlide,
    Page,
    PageText,
    Partner,
    SiteContent,
    SiteSettings,
    SocialLink,
    UploadLimit,
)
from .uploads import rendition_name
from .versioning import VersionedAdminMixin


def _thumb_url(field: Any) -> str:
    return field.storage.url(rendition_name(field.name, 480)) if field else ""


def admin_thumb(field: Any, alt: str = "") -> SafeString | str:
    url = _thumb_url(field)
    if not url:
        return "-"
    return format_html('<img src="{}" alt="{}" class="rlm-thumb" loading="lazy">', url, alt)


class SingletonAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Admin for one-row settings: no add (beyond the first), no delete, list redirects to the row."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponseRedirect:
        if not self.has_view_or_change_permission(request):
            raise PermissionDenied  # refuse before redirecting, so the row's existence is not revealed
        obj = self.model.load()
        opts = self.model._meta
        return HttpResponseRedirect(
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    """System settings: Super Admin only. Website wording and contacts are in Site content."""

    fieldsets = (
        (
            "Staff notifications",
            {
                "fields": ("notification_email",),
                "description": "Alerts never include the content of a submission. Giving, partnership and other "
                "finance enquiries go only to the Finance & Resource Mobilization heads.",
            },
        ),
        ("Approval rules", {"fields": ("vision_mission_approval_required",)}),
        (
            "Analytics (loaded only after visitor consent)",
            {"fields": ("analytics_provider", "analytics_script_url", "analytics_site_id")},
        ),
        (
            "Data retention (days, 0 = keep)",
            {
                "fields": (
                    "retention_prayer_days",
                    "retention_contact_days",
                    "retention_volunteer_days",
                    "retention_event_registration_days",
                    "retention_partnership_days",
                )
            },
        ),
    )


@admin.register(SiteContent)
class SiteContentAdmin(VersionedAdminMixin, SingletonAdmin):
    """Everything visitors see across the site (Technical Team). Every save is versioned and can be rolled back."""

    readonly_fields = ("vision_mission",)
    fieldsets = (
        (
            "Identity",
            {"fields": ("ministry_name", "short_name", "tagline", "logo", "logo_on_dark", "favicon")},
        ),
        ("Scripture", {"fields": ("scripture_reference", "scripture_text")}),
        ("About", {"fields": ("vision_mission", "about_intro", "about_body")}),
        (
            "Contact details (shown publicly)",
            {
                "fields": ("public_email", "public_phone", "whatsapp_number", "address", "footer_text"),
                "description": "Branch addresses and phone numbers are edited on each branch.",
            },
        ),
    )

    @admin.display(description="Vision and mission")
    def vision_mission(self, obj: SiteContent) -> SafeString:
        url = reverse("portal:website:vision_mission")
        return format_html(
            "<p><strong>Vision:</strong> {}</p><p><strong>Mission:</strong> {}</p>"
            '<p class="help">Changed only through <a href="{}">Website &gt; Vision and mission</a> (draft, preview, '
            "approval, publish, with history and rollback).</p>",
            obj.vision,
            obj.mission,
            url,
        )


@admin.register(SocialLink)
class SocialLinkAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("platform", "label", "url", "order", "is_published")
    list_editable = ("order", "is_published")


@admin.register(Page)
class PageAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "slug", "is_published", "show_in_footer", "order", "last_reviewed", "updated_at")
    list_editable = ("show_in_footer", "order")
    prepopulated_fields = {"slug": ("title",)}
    fields = (
        "title",
        "slug",
        "body",
        "last_reviewed",
        "is_published",
        "show_in_footer",
        "order",
        "seo_title",
        "seo_description",
    )


@admin.register(PageText)
class PageTextAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    """Headings and intro text of each page. Rows exist for every place on the site; edit, don't add."""

    list_display = ("label", "heading", "updated_at")
    search_fields = ("label", "heading", "intro")
    readonly_fields = ("label",)
    fields = ("label", "eyebrow", "heading", "highlight", "intro", "seo_title", "seo_description")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # every key is wired into a template; new keys come with code

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(FormOption)
class FormOptionAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Choices offered in the public forms. Switch off instead of deleting, so old answers keep a label."""

    list_display = ("label", "list", "value", "order", "is_active")
    list_editable = ("order", "is_active")
    list_filter = ("list", "is_active")
    search_fields = ("label", "value")
    fields = ("list", "label", "value", "order", "is_active")

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        # The stored code and its list are fixed once created: submissions refer to them.
        return ("list", "value") if obj else ()

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(HeroSlide)
class HeroSlideAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    """Home page hero slides. Reorder with the Order column (lower first) and press Save."""

    list_display = (
        "thumb",
        "title",
        "button_text",
        "order",
        "is_active",
        "status_label",
        "start_at",
        "end_at",
    )
    list_display_links = ("thumb", "title")
    list_editable = ("order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("title", "subtitle")
    readonly_fields = ("preview", "full_preview", "readability")
    fieldsets = (
        (None, {"fields": ("preview", "full_preview", "title", "subtitle", "show_scripture")}),
        (
            "Background",
            {
                "fields": (
                    "background_type",
                    "image",
                    "image_alt",
                    "video",
                    "video_poster",
                    "focal_x",
                    "focal_y",
                    "overlay_opacity",
                    "readability",
                ),
                "description": "Theme colour, photo or a short silent video (with a required poster). A missing "
                "photo or video always falls back to the theme colour.",
            },
        ),
        ("Text", {"fields": ("text_align", "text_tone")}),
        ("Buttons", {"fields": ("button_text", "button_link", "button2_text", "button2_link")}),
        (
            "When to show it",
            {
                "fields": ("order", "is_active", "start_at", "end_at"),
                "description": f"The home page shows up to {HERO_SLIDE_LIMIT} active slides, lowest order first. "
                "Save a new slide switched off, preview it, then switch it on to publish. Every save is kept: "
                "Website > Changes and rollback restores an earlier version.",
            },
        ),
    )

    class Media:
        js = ("admin/rlm-slide-preview.js",)

    @admin.display(description="Preview")
    def thumb(self, obj: HeroSlide) -> SafeString | str:
        return admin_thumb(obj.image, obj.image_alt)

    @admin.display(description="Status")
    def status_label(self, obj: HeroSlide) -> str:
        return obj.status

    @admin.display(description="Live preview")
    def preview(self, obj: HeroSlide | None) -> SafeString:
        """A small mock-up of the slide; static/admin/rlm-slide-preview.js updates it while typing."""
        obj = obj or HeroSlide()
        url = _thumb_url(obj.image)
        return format_html(
            '<div class="rlm-slide-preview" data-slide-preview>'
            '<img src="{}" alt="" data-preview-img{}>'
            '<div class="rlm-slide-preview__text"><strong data-preview-title>{}</strong>'
            "<span data-preview-subtitle>{}</span>"
            '<span class="rlm-slide-preview__btn" data-preview-button{}>{}</span></div></div>'
            '<p class="help">Changes here as you type or choose a new photo. Nothing is saved until you '
            "press Save.</p>",
            url,
            "" if url else SafeString(" hidden"),
            obj.title or "Slide heading",
            obj.subtitle,
            "" if obj.button_text else SafeString(" hidden"),
            obj.button_text,
        )

    @admin.display(description="Preview before publishing")
    def full_preview(self, obj: HeroSlide | None) -> SafeString | str:
        if obj is None or obj.pk is None:
            return "Save the slide (switched off) to preview it full size."
        return format_html(
            '<a href="{}" target="_blank" rel="noopener">Open a full-size preview</a> (also works while the slide '
            "is switched off).",
            reverse("portal:website:hero_preview") + f"?slide={obj.pk}",
        )

    @admin.display(description="Readability")
    def readability(self, obj: HeroSlide | None) -> str:
        from .hero import contrast_message

        if obj is None or obj.pk is None:
            return "Checked after saving."
        return contrast_message(obj) or f"Text contrast about {obj.contrast_ratio}:1 (meets WCAG AA)."

    def save_model(self, request: HttpRequest, obj: HeroSlide, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)
        from .hero import contrast_message

        warning = contrast_message(obj)
        if warning:
            messages.warning(request, warning)

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponse:
        if request.method == "GET":
            live = HeroSlide.objects.live().count()
            if live > HERO_SLIDE_LIMIT:
                messages.warning(
                    request,
                    f"{live} slides are active, but the home page shows only the first {HERO_SLIDE_LIMIT} "
                    "(lowest order). Switch some off or change their order.",
                )
        return super().changelist_view(request, extra_context)


@admin.register(Partner)
class PartnerAdmin(VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    """Logo strip on the home page. It only appears when at least one partner is published."""

    list_display = ("thumb", "name", "website", "order", "is_published")
    list_display_links = ("thumb", "name")
    list_editable = ("order", "is_published")
    search_fields = ("name",)
    fields = ("name", "logo", "website", "order", "is_published")

    @admin.display(description="Logo")
    def thumb(self, obj: Partner) -> SafeString | str:
        return admin_thumb(obj.logo, obj.name)


@admin.register(UploadLimit)
class UploadLimitAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Super Admin only: adjust the size/width/length limits of an upload policy. Formats cannot change here."""

    list_display = ("__str__", "max_mb", "min_width", "max_seconds", "updated_at")
    fields = ("policy", "defaults", "max_mb", "min_width", "max_seconds")
    readonly_fields = ("defaults",)

    def has_module_permission(self, request: HttpRequest) -> bool:
        return bool(getattr(request.user, "is_super_admin", False))

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return self.has_module_permission(request)

    has_add_permission = has_view_permission  # type: ignore[assignment]
    has_change_permission = has_view_permission
    has_delete_permission = has_view_permission

    def formfield_for_dbfield(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        if db_field.name == "policy":
            from django import forms

            from .upload_policy import POLICIES

            return forms.ChoiceField(
                choices=[(p.code, p.label) for p in POLICIES.values()], label="Upload type"
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    @admin.display(description="Built-in rule")
    def defaults(self, obj: UploadLimit | None) -> str:
        from .upload_policy import POLICIES

        policy = POLICIES.get(obj.policy) if obj else None
        return policy.help_text if policy else "Choose an upload type and save to see its built-in rule."
