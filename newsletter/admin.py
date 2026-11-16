from django.contrib import admin

from core.admin_mixins import AuditedAdminMixin, ExportCsvMixin, SubmissionAdminMixin

from .models import Subscriber


@admin.register(Subscriber)
class SubscriberAdmin(SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("audit_label", "status", "confirmed_at", "unsubscribed_at", "created_at")
    list_filter = ("status",)
    search_help_text = "Search by exact email address."
    actions = ["export_csv"]
    readonly_fields = ("email", "name", "status", "confirmed_at", "unsubscribed_at", "created_at")
    export_fields = ["email", "name", "confirmed_at"]

    def get_actions(self, request):  # type: ignore[no-untyped-def]
        actions = super().get_actions(request)
        actions.pop("mark_handled", None)
        return actions

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False  # double opt-in only; no importing of purchased lists

    def export_csv(self, request, queryset):  # type: ignore[no-untyped-def]
        # Only confirmed subscribers may ever be exported for mailing.
        return super().export_csv(request, queryset.filter(status=Subscriber.Status.CONFIRMED))

    export_csv.short_description = "Export confirmed subscribers to CSV"  # type: ignore[attr-defined]
    export_csv.allowed_permissions = ("export",)  # type: ignore[attr-defined]
