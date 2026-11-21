from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from core.admin_mixins import AuditedAdminMixin
from core.versioning import VersionedAdminMixin

from .models import Activity, ActivityCategory

SEO = ("SEO", {"classes": ("collapse",), "fields": ("seo_title", "seo_description")})


class SuperAdminRoutingMixin:
    """The department an activity feeds (staff dashboards, routing) is set by the Super Admin only."""

    def get_readonly_fields(self, request: HttpRequest, obj: Any = None) -> tuple[str, ...]:
        readonly = tuple(super().get_readonly_fields(request, obj))  # type: ignore[misc]
        if not getattr(request.user, "is_super_admin", False):
            readonly += ("department",)
        return readonly


@admin.register(ActivityCategory)
class ActivityCategoryAdmin(SuperAdminRoutingMixin, VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "department", "is_published", "order")
    list_editable = ("order",)
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "summary", "body", "icon")}),
        ("Image", {"fields": ("image", "image_alt")}),
        ("Routing", {"fields": ("department",), "description": "Default department for new activities."}),
        ("Display", {"fields": ("is_published", "order")}),
        SEO,
    )


@admin.register(Activity)
class ActivityAdmin(SuperAdminRoutingMixin, VersionedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "category", "department", "schedule", "is_published", "is_featured", "order")
    list_editable = ("order",)
    list_filter = ("category", "department", "is_published", "is_featured", "branches")
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("branches",)
    fieldsets = (
        (None, {"fields": ("category", "title", "slug", "summary", "body", "icon", "schedule")}),
        ("Image", {"fields": ("image", "image_alt")}),
        ("Where and who", {"fields": ("branches", "department")}),
        ("'Get involved' button", {"fields": ("cta_label", "cta_link")}),
        ("Display", {"fields": ("is_published", "is_featured", "order")}),
        SEO,
    )
