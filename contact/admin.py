from django.contrib import admin

from core.admin_mixins import (
    AuditedAdminMixin,
    ExportCsvMixin,
    FormOptionFieldsMixin,
    SubmissionAdminMixin,
    option_list_filter,
)

from .models import ContactMessage


@admin.register(ContactMessage)
class ContactMessageAdmin(
    SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, FormOptionFieldsMixin, admin.ModelAdmin
):
    audit_views = True
    option_fields = {"topic": "contact_topic"}
    list_display = ("audit_label", "name", "topic_label", "subject", "status", "created_at")
    list_filter = ("status", option_list_filter("topic", "contact_topic", "topic"))
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

    @admin.display(description="Topic", ordering="topic")
    def topic_label(self, obj: ContactMessage) -> str:
        return obj.get_topic_display()
