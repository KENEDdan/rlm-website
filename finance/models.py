"""Finance & Resource Mobilization.

Controls (docs/DECISIONS.md D-019):
* Segregation of duties: whoever records an entry can never approve it; entries above the approval threshold
  need a Super Admin.
* Posted ledger entries are immutable (``save``/``delete`` refuse); corrections are reversing entries that go
  through the same approval.
* Donor personal data is encrypted. Only Finance and the Super Admin see ledgers and donors; other departments
  see only their own budget and spend totals (``finance.portal_views.department_budget``).
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.utils import timezone

from core.crypto import blind_index
from core.fields import EncryptedCharField, EncryptedEmailField, EncryptedTextField
from core.models import SingletonModel, TimeStampedModel
from core.people import Gender, YesNo
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo
from core.validators import validate_safe_link


class FinanceSettings(SingletonModel):
    currency = models.CharField(max_length=3, default="USD")
    approval_threshold = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=Decimal("1000.00"),
        help_text="Entries above this amount must be approved by a Super Admin (Founder).",
    )

    class Meta:
        verbose_name = verbose_name_plural = "finance settings"

    def __str__(self) -> str:
        return "Finance settings"


class Category(models.TextChoices):
    PROGRAMMES = "programmes", "Programmes & events"
    OUTREACH = "outreach", "Outreach & missions"
    PERSONNEL = "personnel", "Personnel & stipends"
    TRAVEL = "travel", "Travel & transport"
    VENUE = "venue", "Venue & accommodation"
    FEEDING = "feeding", "Feeding"
    EQUIPMENT = "equipment", "Equipment & materials"
    MEDIA = "media", "Media & printing"
    CONSTRUCTION = "construction", "Construction & maintenance"
    ADMIN = "admin", "Administration & utilities"
    OTHER = "other", "Other"


class IncomeSource(models.TextChoices):
    OFFERING = "offering", "Offerings & tithes"
    DONATION = "donation", "Individual donations"
    CHURCH = "church", "Partner churches"
    ORGANISATION = "organisation", "Organisations"
    GRANT = "grant", "Grants"
    FUNDRAISING = "fundraising", "Fundraising events"
    OTHER = "other", "Other income"


def current_year() -> int:
    return timezone.localdate().year


class BudgetLine(TimeStampedModel):
    year = models.PositiveSmallIntegerField(default=current_year)
    department = models.ForeignKey("portal.Department", on_delete=models.PROTECT, related_name="budget_lines")
    category = models.CharField(max_length=20, choices=Category.choices)
    name = models.CharField(max_length=160)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0"))]
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-year", "department__order", "name"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["year", "department", "name"], name="unique_budget_line")
        ]

    def __str__(self) -> str:
        return f"{self.year} {self.department} - {self.name}"


class LedgerEntryQuerySet(models.QuerySet):
    def posted(self) -> LedgerEntryQuerySet:
        return self.filter(status=LedgerEntry.Status.POSTED)

    def update(self, **kwargs: Any) -> int:
        if self.filter(status=LedgerEntry.Status.POSTED).exists():
            raise PermissionError("Posted ledger entries cannot be changed; record a reversing entry.")
        return super().update(**kwargs)

    def delete(self) -> tuple[int, dict[str, int]]:
        if self.filter(status=LedgerEntry.Status.POSTED).exists():
            raise PermissionError("Posted ledger entries cannot be deleted; record a reversing entry.")
        return super().delete()


class LedgerEntry(TimeStampedModel):
    class Kind(models.TextChoices):
        INCOME = "income", "Income"
        EXPENSE = "expense", "Expenditure"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Awaiting approval"
        POSTED = "posted", "Approved and posted"
        REJECTED = "rejected", "Rejected"

    number = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    date = models.DateField(default=timezone.localdate, db_index=True)
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, help_text="Always positive (reversals are negative)."
    )
    currency = models.CharField(max_length=3, default="USD")
    department = models.ForeignKey(
        "portal.Department",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
        help_text="Which department spent (or raised) it.",
    )
    budget_line = models.ForeignKey(
        BudgetLine, null=True, blank=True, on_delete=models.PROTECT, related_name="entries"
    )
    category = models.CharField(
        max_length=20, choices=Category.choices, blank=True, help_text="Expenditure only."
    )
    income_source = models.CharField(
        max_length=20, choices=IncomeSource.choices, blank=True, help_text="Income only."
    )
    description = models.CharField(max_length=255)
    counterparty = EncryptedCharField(max_length=200, blank=True, help_text="Payer or payee (encrypted).")
    reference = models.CharField(max_length=60, blank=True, help_text="Receipt / voucher / bank reference")
    receipt = PrivateFileField(
        upload_to=RandomUploadTo("ledger"), blank=True, verbose_name="receipt or voucher"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    recorded_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    posted_at = models.DateTimeField(null=True, blank=True, editable=False)
    rejection_note = models.CharField(max_length=300, blank=True, editable=False)
    reverses = models.OneToOneField(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="reversed_by", editable=False
    )
    donation = models.OneToOneField(
        "giving.Donation",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="ledger_entry",
        editable=False,
    )

    objects = LedgerEntryQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-date", "-pk"]
        verbose_name_plural = "ledger entries"
        permissions: ClassVar = [("export_ledgerentry", "Can export ledger entries")]

    def __str__(self) -> str:
        return f"{self.number or 'Draft'} · {self.get_kind_display()} {self.amount:,.2f} {self.currency}"

    @property
    def audit_label(self) -> str:
        return f"ledger entry #{self.pk}"

    @property
    def is_reversal(self) -> bool:
        return self.reverses_id is not None

    def clean(self) -> None:
        if self.amount is not None and self.amount <= 0 and not self.is_reversal:
            raise ValidationError({"amount": "Enter an amount above zero."})
        if self.kind == self.Kind.EXPENSE and not self.category:
            raise ValidationError({"category": "Choose a category for expenditure."})
        if self.kind == self.Kind.INCOME and not self.income_source:
            raise ValidationError({"income_source": "Choose where the income came from."})
        if (
            self.budget_line_id
            and self.department_id
            and self.budget_line.department_id != self.department_id
        ):
            raise ValidationError({"budget_line": "This budget line belongs to another department."})

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk:
            stored = type(self)._base_manager.filter(pk=self.pk).values_list("status", flat=True).first()
            if stored == self.Status.POSTED:
                raise PermissionError("Posted ledger entries cannot be changed; record a reversing entry.")
        if self.budget_line_id and not self.department_id:
            self.department_id = self.budget_line.department_id
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        if self.status == self.Status.POSTED:
            raise PermissionError("Posted ledger entries cannot be deleted; record a reversing entry.")
        return super().delete(*args, **kwargs)


# ------------------------------------------------------------------------------------------ resource mobilization
class Donor(TimeStampedModel):
    class Kind(models.TextChoices):
        INDIVIDUAL = "individual", "Individual"
        CHURCH = "church", "Church"
        MINISTRY = "ministry", "Ministry"
        ORGANISATION = "organisation", "Organisation"
        INSTITUTION = "institution", "Institution"
        GRANT_MAKER = "grant_maker", "Grant-making body"

    class Stage(models.TextChoices):
        PROSPECT = "prospect", "Prospect"
        CONTACTED = "contacted", "Contacted"
        PROPOSAL = "proposal", "Proposal sent"
        COMMITTED = "committed", "Committed"
        RECEIVED = "received", "Support received"
        LAPSED = "lapsed", "Lapsed"

    kind = models.CharField(max_length=20, choices=Kind.choices, default=Kind.INDIVIDUAL)
    name = EncryptedCharField(max_length=200, verbose_name="name / organisation")
    contact_person = EncryptedCharField(max_length=150, blank=True)
    email = EncryptedEmailField(blank=True)
    email_hash = models.CharField(max_length=64, blank=True, db_index=True, editable=False)
    phone = EncryptedCharField(max_length=30, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=120, blank=True)
    stage = models.CharField(max_length=20, choices=Stage.choices, default=Stage.PROSPECT, db_index=True)
    interests = models.JSONField(default=list, blank=True)
    partnership_types = models.JSONField(default=list, blank=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        help_text="Who looks after this relationship.",
    )
    next_step = models.CharField(max_length=200, blank=True)
    next_step_due = models.DateField(null=True, blank=True)
    notes = EncryptedTextField(blank=True)
    source_enquiry = models.OneToOneField(
        "giving.PartnershipEnquiry",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="donor",
        editable=False,
    )

    class Meta:
        ordering: ClassVar = ["stage", "-updated_at"]
        verbose_name = "donor or partner"
        verbose_name_plural = "donors and partners"
        permissions: ClassVar = [("export_donor", "Can export donors")]

    def __str__(self) -> str:
        return self.name

    @property
    def audit_label(self) -> str:
        return f"donor #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)


class Pledge(TimeStampedModel):
    class Status(models.TextChoices):
        OPEN = "open", "Open"
        PARTIAL = "partial", "Partly received"
        FULFILLED = "fulfilled", "Fulfilled"
        CANCELLED = "cancelled", "Cancelled"

    donor = models.ForeignKey(Donor, on_delete=models.CASCADE, related_name="pledges")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    currency = models.CharField(max_length=3, default="USD")
    purpose = models.CharField(max_length=200, blank=True)
    pledged_on = models.DateField(default=timezone.localdate)
    expected_by = models.DateField(null=True, blank=True)
    received_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)

    class Meta:
        ordering: ClassVar = ["status", "expected_by"]

    def __str__(self) -> str:
        return f"Pledge #{self.pk}: {self.amount:,.2f} {self.currency}"

    @property
    def outstanding(self) -> Decimal:
        if self.status == self.Status.CANCELLED:
            return Decimal("0")
        return max(Decimal("0"), self.amount - self.received_amount)

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.status != self.Status.CANCELLED:
            if self.received_amount >= self.amount:
                self.status = self.Status.FULFILLED
            elif self.received_amount > 0:
                self.status = self.Status.PARTIAL
        super().save(*args, **kwargs)


class GrantOpportunity(TimeStampedModel):
    class Status(models.TextChoices):
        IDENTIFIED = "identified", "Identified"
        DRAFTING = "drafting", "Drafting application"
        SUBMITTED = "submitted", "Submitted"
        AWARDED = "awarded", "Awarded"
        DECLINED = "declined", "Declined"

    funder = models.CharField(max_length=200)
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    deadline = models.DateField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.IDENTIFIED, db_index=True)
    owner = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    link = models.CharField(
        max_length=300, blank=True, validators=[validate_safe_link], help_text="https:// only"
    )
    donor = models.ForeignKey(Donor, null=True, blank=True, on_delete=models.SET_NULL, related_name="grants")
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["deadline"]
        verbose_name_plural = "grant opportunities"

    def __str__(self) -> str:
        return f"{self.title} ({self.funder})"


class Proposal(TimeStampedModel):
    class Kind(models.TextChoices):
        APPEAL = "appeal", "Donor appeal letter"
        PROPOSAL = "proposal", "Funding proposal"
        PARTNERSHIP = "partnership", "Partnership request"
        ACCOUNTABILITY = "accountability", "Accountability report to a donor"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        ACCEPTED = "accepted", "Accepted"
        DECLINED = "declined", "Declined"

    kind = models.CharField(max_length=20, choices=Kind.choices)
    title = models.CharField(max_length=200)
    donor = models.ForeignKey(
        Donor, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals"
    )
    grant = models.ForeignKey(
        GrantOpportunity, null=True, blank=True, on_delete=models.SET_NULL, related_name="proposals"
    )
    amount_requested = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    sent_on = models.DateField(null=True, blank=True)
    document = PrivateFileField(upload_to=RandomUploadTo("proposals"), blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return self.title


# ------------------------------------------------------------------------------------------ finance volunteers
class FinanceVolunteer(TimeStampedModel):
    """Public 'Finance & Accountability Volunteer' form. Vetting never grants access by itself."""

    class Status(models.TextChoices):
        SUBMITTED = "submitted", "Application received"
        REFERENCES = "references", "Checking references"
        INTERVIEW = "interview", "Interview"
        APPROVED = "approved", "Approved (access still needs the Super Admin)"
        DECLINED = "declined", "Not taken forward"

    status = models.CharField(max_length=12, choices=Status.choices, default=Status.SUBMITTED, db_index=True)
    full_name = EncryptedCharField(max_length=150)
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    nationality = models.CharField(max_length=100, blank=True)
    country = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=120, blank=True)
    phone = EncryptedCharField(max_length=30, verbose_name="phone / WhatsApp")
    email = EncryptedEmailField()
    email_hash = models.CharField(max_length=64, db_index=True, editable=False)
    occupation = EncryptedCharField(max_length=150, blank=True)
    education_level = models.CharField(max_length=100)
    field_of_study = models.CharField(max_length=150, blank=True)
    finance_experience = models.CharField(max_length=3, choices=YesNo.choices)
    computer_skills = EncryptedTextField(blank=True, verbose_name="computer skills and software")
    statement = EncryptedTextField(verbose_name="experience and motivation")
    willing_integrity = models.CharField(
        max_length=3, choices=YesNo.choices, verbose_name="willing to serve with honesty and confidentiality"
    )
    declaration = models.BooleanField(default=False)
    consent = models.BooleanField(default=False)
    references_checked = models.BooleanField(default=False)
    vetting_notes = EncryptedTextField(blank=True)
    decided_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    decided_at = models.DateTimeField(null=True, blank=True, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"Finance volunteer #{self.pk}"

    @property
    def audit_label(self) -> str:
        return f"finance volunteer #{self.pk}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.email_hash = blind_index(self.email)
        super().save(*args, **kwargs)
