from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ScopedAdminMixin

from .models import Program


@admin.register(Program)
class ProgramAdmin(ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    department_lookup = "department"
    list_display = ("title", "department", "is_published", "is_featured", "order")
    list_editable = ("order",)
    list_filter = ("is_published", "is_featured", "department")
    search_fields = ("title", "summary")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "summary", "body", "icon", "department")}),
        ("Image", {"fields": ("image", "image_alt")}),
        ("Display", {"fields": ("is_published", "is_featured", "order")}),
        ("SEO", {"classes": ("collapse",), "fields": ("seo_title", "seo_description")}),
    )
