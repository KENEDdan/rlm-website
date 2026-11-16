from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ScopedAdminMixin

from .models import Event


@admin.register(Event)
class EventAdmin(ScopedAdminMixin, AuditedAdminMixin, admin.ModelAdmin):
    branch_lookup = "branch"
    department_lookup = "department"
    list_display = ("title", "start", "branch", "is_published", "registration_open", "capacity", "seats")
    list_filter = ("is_published", "registration_open", "branch", "program")
    search_fields = ("title", "summary", "venue")
    date_hierarchy = "start"
    prepopulated_fields = {"slug": ("title",)}
    fieldsets = (
        (None, {"fields": ("title", "slug", "summary", "description", "program", "branch", "department")}),
        ("When & where", {"fields": ("start", "end", "venue", "address")}),
        ("Registration", {"fields": ("registration_open", "registration_deadline", "capacity")}),
        ("Poster", {"fields": ("poster", "poster_alt")}),
        ("Publication", {"fields": ("is_published", "seo_title", "seo_description")}),
    )

    @admin.display(description="Registered")
    def seats(self, obj: Event) -> int:
        return obj.seats_taken
