from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ExportCsvMixin, SubmissionAdminMixin

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, admin.ModelAdmin):
    audit_views = True
    list_display = ("audit_label", "name", "topic", "subject", "status", "created_at")
    list_filter = ("status", "topic")
    search_help_text = "Search by exact email address or ID number."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("created_at", "handled_by", "handled_at", "consent")
    export_fields = ["id", "created_at", "status", "topic", "name", "email", "phone", "subject", "message"]
    fieldsets = (
        ("Message", {"fields": ("topic", "subject", "message")}),
        ("From", {"fields": ("name", "email", "phone")}),
        (
            "Handling",
            {"fields": ("status", "internal_notes", "handled_by", "handled_at", "consent", "created_at")},
        ),
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False
