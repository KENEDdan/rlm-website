from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ExportCsvMixin, SubmissionAdminMixin

from .models import PrayerRequest


@admin.register(PrayerRequest)
class PrayerRequestAdmin(SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, admin.ModelAdmin):
    """Every opening of a prayer request is written to the audit log."""

    audit_views = True
    list_display = ("audit_label", "keep_confidential", "wants_contact", "status", "created_at")
    list_filter = ("status", "keep_confidential", "wants_contact")
    search_help_text = "Search by exact email address or ID number."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("created_at", "handled_by", "handled_at", "consent")
    export_fields = [
        "id",
        "created_at",
        "status",
        "name",
        "email",
        "phone",
        "keep_confidential",
        "wants_contact",
        "request_text",
    ]
    fieldsets = (
        ("Request", {"fields": ("request_text", "keep_confidential", "wants_contact")}),
        ("Contact (optional)", {"fields": ("name", "email", "phone")}),
        (
            "Handling",
            {"fields": ("status", "internal_notes", "handled_by", "handled_at", "consent", "created_at")},
        ),
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False
