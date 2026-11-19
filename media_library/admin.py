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
    list_display = ("title", "shown_as", "consent_confirmed", "is_approved", "is_published")
    list_filter = ("is_published", "is_approved", "consent_confirmed")
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "body", "photo", "photo_alt", "branch")}),
        (
            "Name and consent",
            {
                "fields": ("person_display_name", "name_display", "full_name_consent", "consent_confirmed"),
                "description": "Visitors only ever see initials or a first name, unless the person gave "
                "explicit consent to show their full name.",
            },
        ),
        (
            "Approval and publishing",
            {
                "fields": ("subject_is_adult", "is_approved", "is_published"),
                "description": "Only testimonies that are approved AND published (with consent) appear on "
                "the website, including the home page slider.",
            },
        ),
        ("Search engines", {"fields": ("seo_title", "seo_description"), "classes": ("collapse",)}),
    )

    @admin.display(description="Shown on the website as")
    def shown_as(self, obj: Testimony) -> str:
        return obj.public_name
