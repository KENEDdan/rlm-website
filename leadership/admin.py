from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin

from .models import Department, Leader


@admin.register(Department)
class DepartmentAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(Leader)
class LeaderAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = (
        "name",
        "role_title",
        "department",
        "branch",
        "confirmation_status",
        "is_published",
        "order",
    )
    list_filter = ("confirmation_status", "is_published", "department", "branch")
    list_editable = ("order",)
    search_fields = ("name", "role_title")
    fieldsets = (
        (None, {"fields": ("name", "role_title", "department", "branch", "bio")}),
        ("Photo", {"fields": ("photo", "photo_alt")}),
        (
            "Publication",
            {
                "fields": ("confirmation_status", "is_published", "order"),
                "description": "A leader appears on the website only when CONFIRMED by leadership AND published.",
            },
        ),
    )
