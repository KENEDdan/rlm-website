from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponseRedirect
from django.urls import reverse

from .admin_mixins import AuditedAdminMixin
from .models import FormOption, Page, PageText, SiteSettings, SocialLink


class SingletonAdmin(AuditedAdminMixin, admin.ModelAdmin):
    """Admin for one-row settings: no add (beyond the first), no delete, list redirects to the row."""

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def changelist_view(self, request: HttpRequest, extra_context: Any = None) -> HttpResponseRedirect:
        obj = self.model.load()
        opts = self.model._meta
        return HttpResponseRedirect(
            reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
        )


@admin.register(SiteSettings)
class SiteSettingsAdmin(SingletonAdmin):
    fieldsets = (
        ("Identity", {"fields": ("ministry_name", "short_name", "tagline", "logo", "logo_on_dark")}),
        ("Scripture", {"fields": ("scripture_reference", "scripture_text")}),
        ("About", {"fields": ("vision", "mission", "about_intro", "about_body")}),
        (
            "Contact details (shown publicly)",
            {"fields": ("public_email", "public_phone", "whatsapp_number", "address", "footer_text")},
        ),
        (
            "Staff notifications",
            {
                "fields": ("notification_email",),
                "description": "Alerts never include the content of a submission.",
            },
        ),
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


@admin.register(SocialLink)
class SocialLinkAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("platform", "label", "url", "order", "is_published")
    list_editable = ("order", "is_published")


@admin.register(Page)
class PageAdmin(AuditedAdminMixin, admin.ModelAdmin):
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
class PageTextAdmin(AuditedAdminMixin, admin.ModelAdmin):
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
