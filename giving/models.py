"""Giving & partnership.

NO card data is ever stored. Card and mobile-money payments must go through a gateway's hosted checkout,
so the PCI scope stays with the gateway (CLAUDE.md rule 11). ``tests/test_giving.py`` asserts that no model in
the project has card-like fields.
"""

from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any, ClassVar

from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import RetainedApplication, SingletonModel, SubmissionModel, TimeStampedModel
from core.site_text import option_label

# Where donors send money. Changed ONLY through BankDetailChange (re-authentication, a second person's
# confirmation, email alerts, history); GivingSettings.save() refuses any other change (fraud prevention).
BANK_FIELDS = (
    "bank_transfer_enabled",
    "account_name",
    "bank_name",
    "account_number",
    "swift_code",
    "branch_name",
    "currency",
    "transfer_instructions",
    "mobile_money_enabled",
    "mobile_money_instructions",
)


class BankDetailsLocked(PermissionError):
    """Bank and payment details were changed outside the confirmation flow."""


class GivingSettings(SingletonModel):
    """How to give. Finance only (never the Technical Team); bank and payment details are protected (BANK_FIELDS)."""

    bank_transfer_enabled = models.BooleanField(
        default=False, help_text="Show bank transfer details on the Give page once they are filled in."
    )
    account_name = models.CharField(max_length=150, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    account_number = EncryptedCharField(
        max_length=60, blank=True, help_text="Stored encrypted; shown on the Give page only when enabled."
    )
    swift_code = models.CharField(max_length=20, blank=True)
    branch_name = models.CharField(max_length=150, blank=True)
    currency = models.CharField(max_length=10, blank=True, help_text="e.g. USD or SSP")
    transfer_instructions = models.TextField(
        blank=True, help_text="Anything donors should know, such as which reference to use."
    )
    mobile_money_enabled = models.BooleanField(default=False)
    mobile_money_instructions = models.TextField(blank=True)
    gateway_enabled = models.BooleanField(
        default=False, help_text="Turn on only after a payment gateway has been integrated and tested."
    )
    gateway_name = models.CharField(max_length=60, blank=True)
    default_currency = models.CharField(max_length=3, default="USD")
    receipt_prefix = models.CharField(max_length=10, default="RLM")
    give_intro = models.TextField(blank=True)
    partnership_intro = models.TextField(blank=True)
    bank_details_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        editable=False,
        help_text="When a second person last confirmed the bank details.",
    )
    bank_details_verified_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )

    class Meta:
        verbose_name = "giving settings"
        verbose_name_plural = "giving settings"

    def __str__(self) -> str:
        return "Giving settings"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk and not getattr(self, "_bank_change_confirmed", False):
            stored = type(self).objects.filter(pk=self.pk).first()
            if stored is not None and any(getattr(stored, f) != getattr(self, f) for f in BANK_FIELDS):
                raise BankDetailsLocked(
                    "Bank and payment details can only be changed through the confirmed change process "
                    "(Staff portal > Finance > Bank details)."
                )
        super().save(*args, **kwargs)

    @property
    def masked_account_number(self) -> str:
        return mask(self.account_number)

    @property
    def has_bank_details(self) -> bool:
        return self.bank_transfer_enabled and bool(
            self.account_name and self.bank_name and self.account_number
        )


def mask(number: str) -> str:
    """Last four characters only, for emails and lists (e.g. "****1234")."""
    digits = "".join(ch for ch in (number or "") if not ch.isspace())
    if not digits:
        return ""
    return "****" + digits[-4:] if len(digits) > 4 else "****"


class BankDetailChange(TimeStampedModel):
    """A proposed change to the bank / payment details: pending until a SECOND authorised person confirms it.

    Proposed by the Finance & Resource Mobilization head (or the Super Admin) after password + 2FA; confirmed or
    rejected by the Founder / Executive Director (another person, also after password + 2FA). Rows are never
    deleted: together they are the full history, including the details that were replaced.
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Waiting for confirmation"
        CONFIRMED = "confirmed", "Confirmed and live"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    bank_transfer_enabled = models.BooleanField(default=False)
    account_name = models.CharField(max_length=150, blank=True)
    bank_name = models.CharField(max_length=150, blank=True)
    account_number = EncryptedCharField(max_length=60, blank=True)
    swift_code = models.CharField(max_length=20, blank=True)
    branch_name = models.CharField(max_length=150, blank=True)
    currency = models.CharField(max_length=10, blank=True)
    transfer_instructions = models.TextField(blank=True)
    mobile_money_enabled = models.BooleanField(default=False)
    mobile_money_instructions = EncryptedTextField(blank=True)
    previous = EncryptedTextField(
        blank=True, editable=False, help_text="The details this change replaced (JSON)."
    )
    reason = models.CharField(max_length=300)
    requested_by = models.ForeignKey(
        "accounts.User", null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    decided_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)
    decision_note = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name = "bank details change"
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["status"], condition=models.Q(status="pending"), name="one_pending_bank_change"
            )
        ]

    def __str__(self) -> str:
        return f"Bank details change #{self.pk} ({self.get_status_display()})"

    @property
    def audit_label(self) -> str:
        return f"bank details change #{self.pk}"

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise PermissionError("Bank detail changes are kept as history and cannot be deleted.")

    @property
    def masked_account_number(self) -> str:
        return mask(self.account_number)


class GivingCategory(TimeStampedModel):
    name = models.CharField(max_length=120, unique=True)
    slug = models.SlugField(max_length=140, unique=True)
    description = models.TextField(blank=True)
    order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["order", "name"]
        verbose_name_plural = "giving categories"

    def __str__(self) -> str:
        return self.name


class CurrentNeed(TimeStampedModel):
    title = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    category = models.ForeignKey(GivingCategory, null=True, blank=True, on_delete=models.SET_NULL)
    target_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    raised_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    order = models.PositiveSmallIntegerField(default=0)
    is_published = models.BooleanField(default=False)

    class Meta:
        ordering: ClassVar = ["order", "-created_at"]

    def __str__(self) -> str:
        return self.title

    @property
    def percent(self) -> int | None:
        if not self.target_amount:
            return None
        return min(100, int(self.raised_amount * 100 / self.target_amount))


class Donation(TimeStampedModel):
    class Provider(models.TextChoices):
        MANUAL_BANK = "manual_bank", "Bank transfer / manual"
        GATEWAY = "gateway", "Online gateway"

    class Status(models.TextChoices):
        PLEDGED = "pledged", "Pledged (awaiting confirmation)"
        PENDING = "pending", "Pending at gateway"
        CONFIRMED = "confirmed", "Confirmed received"
        FAILED = "failed", "Failed"
        CANCELLED = "cancelled", "Cancelled"
        REFUNDED = "refunded", "Refunded"

    category = models.ForeignKey(GivingCategory, null=True, blank=True, on_delete=models.SET_NULL)
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    currency = models.CharField(max_length=3, default="USD")
    provider = models.CharField(max_length=20, choices=Provider.choices, default=Provider.MANUAL_BANK)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PLEDGED, db_index=True)
    donor_name = EncryptedCharField(max_length=150, blank=True)
    donor_email = EncryptedEmailField(blank=True)
    donor_email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    donor_phone = EncryptedCharField(max_length=30, blank=True)
    donor_message = EncryptedTextField(blank=True)
    transfer_reference = EncryptedCharField(max_length=100, blank=True, help_text="Reference the donor used.")
    given_on = models.DateField(null=True, blank=True)
    is_anonymous = models.BooleanField(default=False)
    receipt_number = models.CharField(max_length=40, unique=True, null=True, blank=True, editable=False)
    provider_reference = models.CharField(max_length=120, unique=True, null=True, blank=True, editable=False)
    idempotency_key = models.CharField(max_length=64, unique=True, editable=False)
    confirmed_by = models.ForeignKey(
        "accounts.User", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    finance_notes = EncryptedTextField(blank=True)

    is_finance_queue = True  # new-submission alerts go to the Finance heads only

    class Meta:
        ordering: ClassVar = ["-created_at"]
        permissions: ClassVar = [
            ("export_donation", "Can export donations"),
            ("confirm_donation", "Can confirm donations as received"),
        ]

    def __str__(self) -> str:
        return self.audit_label

    @property
    def audit_label(self) -> str:
        return f"donation #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.donor_email_hash = blind_index(self.donor_email)
        if not self.idempotency_key:
            self.idempotency_key = secrets.token_hex(16)
        super().save(*args, **kwargs)

    def assign_receipt_number(self, prefix: str) -> str:
        if not self.receipt_number:
            self.receipt_number = f"{prefix}-{timezone.now():%Y}-{self.pk:06d}"
        return self.receipt_number


class WebhookEvent(models.Model):
    """Every gateway webhook we accept, keyed by the gateway's event id (idempotency)."""

    provider = models.CharField(max_length=40)
    event_id = models.CharField(max_length=120)
    event_type = models.CharField(max_length=80, blank=True)
    payload_sha256 = models.CharField(max_length=64)
    received_at = models.DateTimeField(auto_now_add=True)
    processed = models.BooleanField(default=False)

    class Meta:
        ordering: ClassVar = ["-received_at"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["provider", "event_id"], name="unique_webhook_event")
        ]

    def __str__(self) -> str:
        return f"{self.provider}:{self.event_id}"


class PartnershipEnquiry(RetainedApplication, SubmissionModel):
    # Admin-managed lists "partner_type" and "partner_interest" (core.FormOption).
    partner_type = models.CharField(max_length=20)
    interest = models.CharField(max_length=20, default="financial")
    name = EncryptedCharField(max_length=150)
    organisation = EncryptedCharField(max_length=200, blank=True)
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    country = models.CharField(max_length=100)
    city = models.CharField(max_length=120, blank=True)
    # Admin-managed lists "partner_area" and "partnership_type" (several choices each).
    areas = models.JSONField(default=list, blank=True)
    other_area = models.CharField(max_length=200, blank=True)
    partnership_types = models.JSONField(default=list, blank=True)
    message = EncryptedTextField(blank=True)
    consent = models.BooleanField(default=False)
    internal_notes = EncryptedTextField(blank=True)

    is_finance_queue = True  # new-submission alerts go to the Finance heads only

    class Meta(SubmissionModel.Meta):
        verbose_name = "partnership registration"
        verbose_name_plural = "partnership registrations"
        permissions: ClassVar = [("export_partnershipenquiry", "Can export partnership enquiries")]

    def get_partner_type_display(self) -> str:
        return option_label("partner_type", self.partner_type)

    def get_interest_display(self) -> str:
        return option_label("partner_interest", self.interest)

    def get_areas_display(self) -> str:
        return ", ".join(option_label("partner_area", v) for v in self.areas or [])

    def get_partnership_types_display(self) -> str:
        return ", ".join(option_label("partnership_type", v) for v in self.partnership_types or [])

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
