from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ScopedAdminMixin
from core.versioning import VersionedAdminMixin

from .models import Branch, Country


@admin.register(Country)
class CountryAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "code", "order")
    list_editable = ("order",)


@admin.register(Branch)
class BranchAdmin(VersionedAdminMixin, ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    branch_lookup = "id"
    list_display = ("name", "country", "city", "is_published", "order")
    list_filter = ("country", "is_published")
    search_fields = ("name", "city")
    prepopulated_fields = {"slug": ("name",)}
    fieldsets = (
        (
            None,
            {
                "fields": (
                    "name",
                    "slug",
                    "country",
                    "city",
                    "summary",
                    "description",
                    "is_published",
                    "order",
                )
            },
        ),
        ("Activities & meetings", {"fields": ("activities", "meeting_times")}),
        (
            "Contact (optional, shown publicly)",
            {"fields": ("contact_email", "contact_phone", "address", "map_url")},
        ),
        ("Image", {"fields": ("image", "image_alt")}),
        ("SEO", {"classes": ("collapse",), "fields": ("seo_title", "seo_description")}),
    )

    def get_readonly_fields(self, request, obj=None):  # type: ignore[no-untyped-def]
        # Branch Coordinators may edit their branch's content but not move it or rename its URL.
        if self._is_scoped(request):
            return ("slug", "country", "is_published", "order")
        return ()

    def get_prepopulated_fields(self, request, obj=None):  # type: ignore[no-untyped-def]
        return {} if self._is_scoped(request) else super().get_prepopulated_fields(request, obj)
