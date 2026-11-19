from django.contrib import admin

from core.admin_mixins import (
    AuditedAdminMixin,
    ExportCsvMixin,
    FormOptionFieldsMixin,
    ScopedAdminMixin,
    SubmissionAdminMixin,
    option_list_filter,
)

from .models import EventRegistration, VolunteerApplication


@admin.register(VolunteerApplication)
class VolunteerApplicationAdmin(
    ScopedAdminMixin,
    SubmissionAdminMixin,
    ExportCsvMixin,
    AuditedAdminMixin,
    FormOptionFieldsMixin,
    admin.ModelAdmin,
):
    audit_views = True
    option_fields = {"interests": "volunteer_interest", "availability": "volunteer_availability"}
    multi_option_fields = {"interests"}
    branch_lookup = "branch"
    list_display = (
        "audit_label",
        "full_name",
        "location",
        "branch",
        "availability_label",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        option_list_filter("availability", "volunteer_availability", "availability"),
        "branch",
        "country",
    )
    search_fields = ("location",)
    search_help_text = "Search by exact email address, ID number or location."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("created_at", "handled_by", "handled_at", "consent")
    export_fields = [
        "id",
        "created_at",
        "status",
        "full_name",
        "email",
        "phone",
        "country",
        "location",
        "branch",
        "church_affiliation",
        "interests",
        "availability",
        "skills",
        "previous_experience",
    ]
    fieldsets = (
        (
            "Person",
            {
                "fields": (
                    "full_name",
                    "email",
                    "phone",
                    "country",
                    "location",
                    "branch",
                    "church_affiliation",
                )
            },
        ),
        ("Service", {"fields": ("interests", "availability", "skills", "previous_experience", "testimony")}),
        (
            "Handling",
            {"fields": ("status", "internal_notes", "handled_by", "handled_at", "consent", "created_at")},
        ),
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False  # submissions come from the public form only

    @admin.display(description="Availability", ordering="availability")
    def availability_label(self, obj: VolunteerApplication) -> str:
        return obj.get_availability_display()


@admin.register(EventRegistration)
class EventRegistrationAdmin(
    ScopedAdminMixin, SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, admin.ModelAdmin
):
    audit_views = True
    branch_lookup = "event__branch"
    list_display = (
        "audit_label",
        "full_name",
        "event",
        "attendees",
        "registration_status",
        "status",
        "created_at",
    )
    list_filter = ("registration_status", "status", "event")
    search_help_text = "Search by exact email address or ID number."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("event", "created_at", "handled_by", "handled_at", "consent")
    export_fields = [
        "id",
        "created_at",
        "event",
        "full_name",
        "email",
        "phone",
        "attendees",
        "registration_status",
        "notes",
    ]
    fields = (
        "event",
        "full_name",
        "email",
        "phone",
        "attendees",
        "notes",
        "registration_status",
        "status",
        "handled_by",
        "handled_at",
        "consent",
        "created_at",
    )

    def has_add_permission(self, request):  # type: ignore[no-untyped-def]
        return False
