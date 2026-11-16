from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ScopedAdminMixin

from .models import Album, Photo, Report, Testimony, Video


class PhotoInline(admin.TabularInline):
    model = Photo
    extra = 3
    fields = ("image", "alt_text", "caption", "order", "is_published")


@admin.register(Album)
class AlbumAdmin(ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"
    list_display = ("title", "date", "branch", "is_published")
    list_filter = ("is_published", "branch")
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    inlines = [PhotoInline]
    fields = (
        "title",
        "slug",
        "description",
        "date",
        "branch",
        "event",
        "cover",
        "cover_alt",
        "is_published",
        "seo_title",
        "seo_description",
    )


@admin.register(Photo)
class PhotoAdmin(ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    branch_lookup = "album__branch"
    list_display = ("__str__", "album", "is_published", "order")
    list_filter = ("album", "is_published")

    def formfield_for_foreignkey(self, db_field, request, **kwargs):  # type: ignore[no-untyped-def]
        if db_field.name == "album" and self._is_scoped(request):
            kwargs["queryset"] = Album.objects.filter(branch_id=request.user.branch_id)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)


@admin.register(Video)
class VideoAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "youtube_id", "recorded_on", "is_published")
    list_filter = ("is_published",)
    search_fields = ("title",)
    prepopulated_fields = {"slug": ("title",)}
    fields = (
        "title",
        "slug",
        "youtube_url",
        "description",
        "album",
        "recorded_on",
        "is_published",
        "seo_title",
        "seo_description",
    )


@admin.register(Report)
class ReportAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "year", "is_published")
    prepopulated_fields = {"slug": ("title",)}
    fields = ("title", "slug", "year", "summary", "file", "is_published", "seo_title", "seo_description")


@admin.register(Testimony)
class TestimonyAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("title", "person_display_name", "consent_confirmed", "is_published")
    list_filter = ("is_published", "consent_confirmed")
    prepopulated_fields = {"slug": ("title",)}
    fields = (
        "title",
        "slug",
        "person_display_name",
        "body",
        "photo",
        "photo_alt",
        "branch",
        "consent_confirmed",
        "is_published",
        "seo_title",
        "seo_description",
    )
