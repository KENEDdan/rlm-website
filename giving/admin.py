from __future__ import annotations

from typing import Any

from django.contrib import admin, messages
from django.db.models import QuerySet
from django.http import HttpRequest

from core.admin import SingletonAdmin
from core.admin_mixins import (
    AuditedAdminMixin,
    ExportCsvMixin,
    FormOptionFieldsMixin,
    SubmissionAdminMixin,
    option_list_filter,
)

from . import services
from .models import CurrentNeed, Donation, GivingCategory, GivingSettings, PartnershipEnquiry, WebhookEvent


@admin.register(GivingSettings)
class GivingSettingsAdmin(SingletonAdmin):
    """Only Founder and Finance have permissions on this model (see accounts/roles.py)."""

    audit_views = True
    readonly_fields = ("bank_details",)
    fieldsets = (
        (
            "Bank and payment details",
            {
                "fields": ("bank_details",),
                "description": "Changed only in the staff portal (Finance > Bank details): re-authentication, a "
                "second person's confirmation, email alerts and full history. Never here.",
            },
        ),
        (
            "Online gateway (future)",
            {
                "fields": ("gateway_enabled", "gateway_name"),
                "description": "Leave off until a gateway is integrated.",
            },
        ),
        (
            "Receipts & text",
            {"fields": ("default_currency", "receipt_prefix", "give_intro", "partnership_intro")},
        ),
    )

    @admin.display(description="Bank details")
    def bank_details(self, obj: GivingSettings) -> str:
        verified = f"{obj.bank_details_verified_at:%d %b %Y}" if obj.bank_details_verified_at else "never"
        shown = "shown" if obj.has_bank_details else "not shown"
        return f"Account ending {obj.masked_account_number or '(none)'}, {shown} on the Give page; last verified {verified}."


@admin.register(GivingCategory)
class GivingCategoryAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = ("name", "is_active", "order")
    list_editable = ("is_active", "order")
    prepopulated_fields = {"slug": ("name",)}


@admin.register(CurrentNeed)
class CurrentNeedAdmin(AuditedAdminMixin, admin.ModelAdmin):
    list_display = (
        "title",
        "category",
        "target_amount",
        "raised_amount",
        "currency",
        "is_published",
        "order",
    )
    list_editable = ("is_published", "order")


@admin.register(Donation)
class DonationAdmin(SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, admin.ModelAdmin):
    audit_views = True
    email_hash_field = "donor_email_hash"
    list_display = (
        "audit_label",
        "amount",
        "currency",
        "category",
        "provider",
        "status",
        "receipt_number",
        "created_at",
    )
    list_filter = ("status", "provider", "category", "currency")
    search_help_text = "Search by exact donor email, ID number."
    actions = ["confirm_received", "export_csv"]
    readonly_fields = (
        "provider",
        "receipt_number",
        "provider_reference",
        "idempotency_key",
        "confirmed_by",
        "confirmed_at",
        "created_at",
    )
    export_fields = [
        "id",
        "created_at",
        "status",
        "amount",
        "currency",
        "category",
        "provider",
        "receipt_number",
        "donor_name",
        "donor_email",
        "transfer_reference",
        "given_on",
        "is_anonymous",
    ]
    fieldsets = (
        ("Gift", {"fields": ("amount", "currency", "category", "given_on", "transfer_reference", "status")}),
        ("Donor", {"fields": ("donor_name", "donor_email", "donor_phone", "donor_message", "is_anonymous")}),
        (
            "Finance",
            {
                "fields": (
                    "finance_notes",
                    "provider",
                    "receipt_number",
                    "provider_reference",
                    "idempotency_key",
                    "confirmed_by",
                    "confirmed_at",
                    "created_at",
                )
            },
        ),
    )

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        actions = super().get_actions(request)
        actions.pop("mark_handled", None)
        return actions

    def has_confirm_permission(self, request: HttpRequest) -> bool:
        return request.user.has_perm("giving.confirm_donation")

    @admin.action(description="Confirm selected gifts as received (issues receipt)", permissions=["confirm"])
    def confirm_received(self, request: HttpRequest, queryset: QuerySet) -> None:
        done = 0
        for donation in queryset:
            if services.confirm_donation(donation, request=request):
                done += 1
        messages.success(
            request, f"{done} gift(s) confirmed; receipts are being emailed where an address was given."
        )


@admin.register(WebhookEvent)
class WebhookEventAdmin(admin.ModelAdmin):
    list_display = ("provider", "event_id", "event_type", "processed", "received_at")
    readonly_fields = ("provider", "event_id", "event_type", "payload_sha256", "processed", "received_at")

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(PartnershipEnquiry)
class PartnershipEnquiryAdmin(
    SubmissionAdminMixin, ExportCsvMixin, AuditedAdminMixin, FormOptionFieldsMixin, admin.ModelAdmin
):
    audit_views = True
    option_fields = {"partner_type": "partner_type", "interest": "partner_interest"}
    list_display = (
        "audit_label",
        "name",
        "partner_type_label",
        "interest_label",
        "country",
        "status",
        "created_at",
    )
    list_filter = (
        "status",
        option_list_filter("partner_type", "partner_type", "partner type"),
        option_list_filter("interest", "partner_interest", "interest"),
    )

    @admin.display(description="Partner type", ordering="partner_type")
    def partner_type_label(self, obj: PartnershipEnquiry) -> str:
        return obj.get_partner_type_display()

    @admin.display(description="Interest", ordering="interest")
    def interest_label(self, obj: PartnershipEnquiry) -> str:
        return obj.get_interest_display()

    search_help_text = "Search by exact email address or ID number."
    actions = ["mark_handled", "export_csv"]
    readonly_fields = ("created_at", "handled_by", "handled_at", "consent")
    export_fields = [
        "id",
        "created_at",
        "status",
        "partner_type",
        "interest",
        "name",
        "organisation",
        "email",
        "phone",
        "country",
        "message",
    ]

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False
