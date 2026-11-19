"""Logistics & Procurement: transparent procurement, assets and inventory, event logistics."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.fields import EncryptedCharField, EncryptedEmailField
from core.models import TimeStampedModel
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo

MIN_QUOTATIONS = 3


class Supplier(TimeStampedModel):
    name = models.CharField(max_length=200)
    category = models.CharField(
        max_length=120, blank=True, help_text="e.g. Sound equipment, Printing, Transport"
    )
    contact_person = EncryptedCharField(max_length=150, blank=True)
    phone = EncryptedCharField(max_length=30, blank=True)
    email = EncryptedEmailField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(5)],
        help_text="1 (poor) to 5 (excellent)",
    )
    is_active = models.BooleanField(default=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return self.name


class PurchaseRequest(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted: collecting quotations"
        RECOMMENDED = "recommended", "Supplier recommended: awaiting Finance"
        BUDGET_CONFIRMED = "budget_confirmed", "Budget confirmed: awaiting approval"
        APPROVED = "approved", "Approved"
        ORDERED = "ordered", "Purchase order issued"
        RECEIVED = "received", "Goods received"
        CLOSED = "closed", "Closed"
        REJECTED = "rejected", "Rejected"
        CANCELLED = "cancelled", "Cancelled"

    OPEN = (
        Status.DRAFT,
        Status.SUBMITTED,
        Status.RECOMMENDED,
        Status.BUDGET_CONFIRMED,
        Status.APPROVED,
        Status.ORDERED,
    )

    number = models.CharField(max_length=20, unique=True, null=True, blank=True, editable=False)
    title = models.CharField(max_length=200)
    requesting_department = models.ForeignKey(
        "portal.Department", on_delete=models.PROTECT, related_name="purchase_requests"
    )
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    event = models.ForeignKey("events.Event", null=True, blank=True, on_delete=models.SET_NULL)
    description = models.TextField(help_text="What is needed, quantities and specifications.")
    needed_by = models.DateField(null=True, blank=True)
    estimated_cost = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    currency = models.CharField(max_length=3, default="USD")
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.DRAFT, db_index=True)
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    recommended_quotation = models.ForeignKey(
        "Quotation", null=True, blank=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    recommendation_note = models.TextField(blank=True, editable=False)
    budget_line = models.ForeignKey(
        "finance.BudgetLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_requests",
        editable=False,
    )
    budget_confirmed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    budget_confirmed_at = models.DateTimeField(null=True, blank=True, editable=False)
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    approved_at = models.DateTimeField(null=True, blank=True, editable=False)
    rejection_note = models.CharField(max_length=300, blank=True, editable=False)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.number or 'Draft'} · {self.title}"

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.SUBMITTED)


class Quotation(TimeStampedModel):
    request = models.ForeignKey(PurchaseRequest, on_delete=models.CASCADE, related_name="quotations")
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="quotations")
    amount = models.DecimalField(
        max_digits=14, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))]
    )
    delivery_days = models.PositiveSmallIntegerField(
        null=True, blank=True, help_text="Promised delivery time"
    )
    valid_until = models.DateField(null=True, blank=True)
    file = PrivateFileField(
        upload_to=RandomUploadTo("quotations"), blank=True, verbose_name="quotation document"
    )
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["amount"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["request", "supplier"], name="one_quotation_per_supplier")
        ]

    def __str__(self) -> str:
        return f"{self.supplier}: {self.amount:,.2f}"


class PurchaseOrder(TimeStampedModel):
    request = models.OneToOneField(PurchaseRequest, on_delete=models.PROTECT, related_name="order")
    number = models.CharField(max_length=20, unique=True, editable=False)
    supplier = models.ForeignKey(Supplier, on_delete=models.PROTECT, related_name="orders")
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    issued_on = models.DateField(default=timezone.localdate)
    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    expected_delivery = models.DateField(null=True, blank=True)

    class Meta:
        ordering: ClassVar = ["-issued_on"]

    def __str__(self) -> str:
        return f"{self.number} · {self.supplier}"

    @property
    def is_late(self) -> bool:
        delivered = self.deliveries.filter(is_complete=True).exists()
        return bool(
            self.expected_delivery and not delivered and self.expected_delivery < timezone.localdate()
        )


class DeliveryNote(TimeStampedModel):
    order = models.ForeignKey(PurchaseOrder, on_delete=models.PROTECT, related_name="deliveries")
    delivered_on = models.DateField(default=timezone.localdate)
    note_number = models.CharField(max_length=60, blank=True, help_text="Supplier's delivery note number")
    is_complete = models.BooleanField(
        default=True, help_text="Everything ordered has arrived in good condition."
    )
    condition_notes = models.TextField(blank=True)
    received_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    file = PrivateFileField(upload_to=RandomUploadTo("deliveries"), blank=True)

    class Meta:
        ordering: ClassVar = ["-delivered_on"]

    def __str__(self) -> str:
        return f"Delivery {self.delivered_on:%d %b %Y} for {self.order.number}"


# ------------------------------------------------------------------------------------------ assets & inventory
class InventoryItem(TimeStampedModel):
    class Kind(models.TextChoices):
        ASSET = "asset", "Asset / equipment"
        CONSUMABLE = "consumable", "Consumable / supply"

    class Condition(models.TextChoices):
        NEW = "new", "New"
        GOOD = "good", "Good"
        FAIR = "fair", "Fair"
        POOR = "poor", "Poor"
        BROKEN = "broken", "Broken / out of service"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=12, choices=Kind.choices, default=Kind.ASSET)
    category = models.CharField(max_length=120, blank=True)
    tag = models.CharField(max_length=60, blank=True, help_text="Asset tag or serial number")
    quantity = models.PositiveIntegerField(default=1)
    unit = models.CharField(max_length=30, default="pcs")
    reorder_level = models.PositiveIntegerField(
        default=0, help_text="Alert when quantity falls to this level"
    )
    condition = models.CharField(max_length=10, choices=Condition.choices, default=Condition.GOOD)
    location = models.CharField(max_length=160, blank=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    custodian = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    maintenance_interval_days = models.PositiveIntegerField(null=True, blank=True)
    last_maintenance = models.DateField(null=True, blank=True)
    purchase_order = models.ForeignKey(
        PurchaseOrder, null=True, blank=True, on_delete=models.SET_NULL, editable=False
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["name"]

    def __str__(self) -> str:
        return f"{self.name}{f' ({self.tag})' if self.tag else ''}"

    @property
    def next_maintenance(self) -> Any:
        if not self.maintenance_interval_days:
            return None
        base = self.last_maintenance or self.created_at.date()
        return base + timedelta(days=self.maintenance_interval_days)

    @property
    def is_low(self) -> bool:
        return self.quantity <= self.reorder_level

    @property
    def available(self) -> int:
        out = sum(loan.quantity for loan in self.loans.filter(returned_on__isnull=True))
        return max(0, self.quantity - out)


class AssetLoan(TimeStampedModel):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="loans")
    borrower = models.CharField(max_length=150, help_text="Person or team")
    department = models.ForeignKey("portal.Department", null=True, blank=True, on_delete=models.SET_NULL)
    quantity = models.PositiveIntegerField(default=1)
    out_on = models.DateField(default=timezone.localdate)
    due_back = models.DateField(null=True, blank=True)
    returned_on = models.DateField(null=True, blank=True)
    return_condition = models.CharField(max_length=10, choices=InventoryItem.Condition.choices, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["returned_on", "due_back"]
        verbose_name = "check-out"

    def __str__(self) -> str:
        return f"{self.item} → {self.borrower}"

    @property
    def is_overdue(self) -> bool:
        return bool(self.returned_on is None and self.due_back and self.due_back < timezone.localdate())


class MaintenanceRecord(TimeStampedModel):
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name="maintenance")
    date = models.DateField(default=timezone.localdate)
    description = models.CharField(max_length=300)
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    done_by = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering: ClassVar = ["-date"]

    def __str__(self) -> str:
        return f"{self.item}: {self.description}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        super().save(*args, **kwargs)
        item = self.item
        if item.last_maintenance is None or item.last_maintenance < self.date:
            InventoryItem.objects.filter(pk=item.pk).update(last_maintenance=self.date)


# ------------------------------------------------------------------------------------------ event logistics
class LogisticsPlan(TimeStampedModel):
    class Kind(models.TextChoices):
        CONFERENCE = "conference", "Conference"
        CRUSADE = "crusade", "Crusade"
        FELLOWSHIP = "fellowship", "Fellowship"
        OUTREACH = "outreach", "Outreach"
        OTHER = "other", "Other"

    class Status(models.TextChoices):
        PLANNING = "planning", "Planning"
        READY = "ready", "Ready"
        DONE = "done", "Done"

    title = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    event = models.ForeignKey(
        "events.Event", null=True, blank=True, on_delete=models.SET_NULL, related_name="logistics_plans"
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    location = models.CharField(max_length=200, blank=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    expected_attendance = models.PositiveIntegerField(null=True, blank=True)
    coordinator = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PLANNING)

    class Meta:
        ordering: ClassVar = ["start_date"]

    def __str__(self) -> str:
        return self.title

    @property
    def progress(self) -> int:
        total = self.tasks.count()
        return int(self.tasks.filter(done=True).count() * 100 / total) if total else 0


class LogisticsTask(TimeStampedModel):
    class Category(models.TextChoices):
        TRANSPORT = "transport", "Transport"
        ACCOMMODATION = "accommodation", "Accommodation"
        FEEDING = "feeding", "Feeding"
        EQUIPMENT = "equipment", "Equipment"
        VENUE = "venue", "Venue"
        OTHER = "other", "Other"

    plan = models.ForeignKey(LogisticsPlan, on_delete=models.CASCADE, related_name="tasks")
    category = models.CharField(max_length=15, choices=Category.choices)
    description = models.CharField(max_length=300)
    quantity = models.CharField(max_length=60, blank=True, help_text="e.g. 2 buses, 150 meals")
    estimated_cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    responsible = models.CharField(max_length=150, blank=True)
    due = models.DateField(null=True, blank=True)
    done = models.BooleanField(default=False)

    class Meta:
        ordering: ClassVar = ["done", "due", "category"]

    def __str__(self) -> str:
        return f"{self.get_category_display()}: {self.description}"
