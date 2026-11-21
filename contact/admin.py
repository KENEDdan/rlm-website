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
    list_display = ("audit_label", "name", "category", "topic_label", "subject", "status", "created_at")
    list_filter = ("status", "category", option_list_filter("topic", "contact_topic", "topic"))
    search_help_text = "Search by exact email address or ID number."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("created_at", "handled_by", "handled_at", "consent", "category")
    export_fields = ["id", "created_at", "status", "topic", "name", "email", "phone", "subject", "message"]
    fieldsets = (
        ("Message", {"fields": ("category", "topic", "subject", "message")}),
        ("From", {"fields": ("name", "email", "phone")}),
        (
            "Handling",
            {"fields": ("status", "internal_notes", "handled_by", "handled_at", "consent", "created_at")},
        ),
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False

    def get_queryset(self, request):  # type: ignore[no-untyped-def]
        # Giving/finance and partnership messages live ONLY in the Finance queue (staff portal); only the
        # Super Admin sees both here.
        qs = super().get_queryset(request)
        return qs if getattr(request.user, "is_super_admin", False) else qs.general()

    @admin.display(description="Topic", ordering="topic")
    def topic_label(self, obj: ContactMessage) -> str:
        return obj.get_topic_display()
