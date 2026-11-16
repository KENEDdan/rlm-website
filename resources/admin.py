from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin

from .models import Resource, ResourceCategory, Series


@admin.register(ResourceCategory)
class ResourceCategoryAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Series)
class SeriesAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title",)
    prepopulated_fields = {"slug": ("title",)}


@admin.register(Resource)
class ResourceAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "kind", "speaker", "date", "category", "is_published")
    list_filter = ("kind", "is_published", "category", "series")
    search_fields = ("title", "speaker", "scripture")
    date_hierarchy = "date"
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("kind", "title", "slug", "speaker", "date", "scripture", "summary", "body")}),
        ("Grouping", {"fields": ("category", "series")}),
        ("Media", {"fields": ("youtube_url", "audio", "pdf", "thumbnail")}),
        ("Publication", {"fields": ("is_published", "seo_title", "seo_description")}),
    )
