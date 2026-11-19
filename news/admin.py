from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ScopedAdminMixin

from .models import Post


@admin.register(Post)
class PostAdmin(ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"
    list_display = ("title", "kind", "status", "publish_at", "branch", "author")
    list_filter = ("status", "kind", "branch")
    search_fields = ("title", "summary")
    date_hierarchy = "publish_at"
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "kind", "summary", "body")}),
        ("Image", {"fields": ("image", "image_alt")}),
        ("Scope", {"fields": ("branch", "department")}),
        ("Publishing", {"fields": ("status", "publish_at")}),
        ("SEO", {"classes": ("collapse",), "fields": ("seo_title", "seo_description")}),
    )

    def save_model(self, request, obj, form, change):  # type: ignore[no-untyped-def]
        if not change:
            obj.author = request.user
        super().save_model(request, obj, form, change)
