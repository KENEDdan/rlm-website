"""Development & Infrastructure: capital projects, properties, maintenance, contractors and partners."""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from core.fields import EncryptedCharField, EncryptedEmailField
from core.models import TimeStampedModel
from core.private_files import PrivateFileField
from core.uploads import RandomUploadTo


class Contractor(TimeStampedModel):
    class Kind(models.TextChoices):
        CONTRACTOR = "contractor", "Building contractor"
        ARCHITECT = "architect", "Architect"
        ENGINEER = "engineer", "Engineer"
        SURVEYOR = "surveyor", "Quantity surveyor"
        PARTNER = "partner", "Development partner"
        OTHER = "other", "Other professional"

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    specialty = models.CharField(max_length=160, blank=True)
    contact_person = EncryptedCharField(max_length=150, blank=True)
    phone = EncryptedCharField(max_length=30, blank=True)
    email = EncryptedEmailField(blank=True)
    rating = models.PositiveSmallIntegerField(
        null=True, blank=True, validators=[MinValueValidator(1), MaxValueValidator(5)]
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["name"]
        verbose_name = "contractor / professional / partner"
        verbose_name_plural = "contractors, professionals and partners"

    def __str__(self) -> str:
        return f"{self.name} ({self.get_kind_display()})"


class Property(TimeStampedModel):
    class Kind(models.TextChoices):
        LAND = "land", "Land / plot"
        BUILDING = "building", "Building"

    class Tenure(models.TextChoices):
        OWNED = "owned", "Owned"
        LEASED = "leased", "Leased / rented"
        DONATED = "donated", "Donated / on loan"
        ACQUIRING = "acquiring", "Being acquired"

    name = models.CharField(max_length=160)
    kind = models.CharField(max_length=10, choices=Kind.choices)
    location = models.CharField(max_length=200)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    size = models.CharField(max_length=60, blank=True, help_text="e.g. 50 x 100 ft, 3 rooms")
    tenure = models.CharField(max_length=10, choices=Tenure.choices, default=Tenure.OWNED)
    title_reference = EncryptedCharField(
        max_length=120, blank=True, help_text="Title deed / lease number (encrypted)"
    )
    acquired_on = models.DateField(null=True, blank=True)
    title_document = PrivateFileField(upload_to=RandomUploadTo("property"), blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["name"]
        verbose_name_plural = "properties and land"

    def __str__(self) -> str:
        return self.name


class Project(TimeStampedModel):
    class Kind(models.TextChoices):
        OFFICE = "office", "Offices"
        HALL = "hall", "Conference hall"
        HOSTEL = "hostel", "Hostel"
        TRAINING = "training", "Training centre"
        WORSHIP = "worship", "Worship facility"
        RENOVATION = "renovation", "Renovation"
        OTHER = "other", "Other"

    class Phase(models.TextChoices):
        CONCEPT = "concept", "Concept"
        FEASIBILITY = "feasibility", "Feasibility"
        DESIGN = "design", "Design"
        PERMITS = "permits", "Permits & approvals"
        FUNDRAISING = "fundraising", "Fundraising"
        CONSTRUCTION = "construction", "Construction"
        HANDOVER = "handover", "Handover / snagging"
        COMPLETED = "completed", "Completed"
        ON_HOLD = "on_hold", "On hold"

    ACTIVE = (
        Phase.CONCEPT,
        Phase.FEASIBILITY,
        Phase.DESIGN,
        Phase.PERMITS,
        Phase.FUNDRAISING,
        Phase.CONSTRUCTION,
        Phase.HANDOVER,
    )

    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=12, choices=Kind.choices)
    phase = models.CharField(max_length=12, choices=Phase.choices, default=Phase.CONCEPT, db_index=True)
    branch = models.ForeignKey("branches.Branch", null=True, blank=True, on_delete=models.SET_NULL)
    site = models.ForeignKey(
        Property,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="projects",
        verbose_name="property",
    )
    description = models.TextField(blank=True)
    budget_line = models.OneToOneField(
        "finance.BudgetLine",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="project",
        help_text="The project's cost centre in the Finance budget. Its costs are the ledger entries tagged with the project.",
    )
    funding_secured = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0"))
    currency = models.CharField(max_length=3, default="USD")
    start_date = models.DateField(null=True, blank=True)
    target_end = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    project_manager = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    contractors = models.ManyToManyField(Contractor, blank=True, related_name="projects")

    class Meta:
        ordering: ClassVar = ["start_date", "name"]

    def __str__(self) -> str:
        return self.name

    # ------------------------------------------------------------------ money: read from the Finance ledger
    @property
    def budget(self) -> Decimal:
        if not self.budget_line_id:
            return Decimal("0")
        from finance.approvals import line_position

        return line_position(self.budget_line).total

    def _ledger(self) -> Any:
        from finance.models import LedgerEntry

        return LedgerEntry.objects.filter(project=self, kind=LedgerEntry.Kind.EXPENSE)

    @property
    def spent(self) -> Decimal:
        return self._ledger().filter(status="posted").aggregate(t=Sum("amount"))["t"] or Decimal("0")

    @property
    def committed(self) -> Decimal:
        """Costs submitted and waiting for approval, plus approved commitments charged to the project's line."""
        waiting = self._ledger().filter(status="submitted").aggregate(t=Sum("amount"))["t"] or Decimal("0")
        if not self.budget_line_id:
            return waiting
        from finance.approvals import line_position

        return waiting + line_position(self.budget_line).committed

    def finance_summary(self) -> dict[str, Any]:
        budget, spent, committed = self.budget, self.spent, self.committed
        total = self.milestones.count()
        done = self.milestones.filter(completed_on__isnull=False).count()
        return {
            "budget": budget,
            "committed": committed,
            "spent": spent,
            "remaining": budget - spent - committed,
            "variance": budget - spent - committed,
            "spent_pct": int(spent * 100 / budget) if budget else None,
            "milestones_pct": int(done * 100 / total) if total else None,
            "overspent": spent > budget if budget else spent > 0,
            "unbudgeted": self._ledger().filter(unbudgeted=True).exclude(status="rejected").count(),
            "no_budget_line": not self.budget_line_id,
        }

    @property
    def funding_gap(self) -> Decimal:
        return max(Decimal("0"), self.budget - self.funding_secured)

    @property
    def latest_progress(self) -> int | None:
        visit = self.site_visits.first()
        return visit.progress_percent if visit else None


class Milestone(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="milestones")
    title = models.CharField(max_length=200)
    due_date = models.DateField()
    completed_on = models.DateField(null=True, blank=True)
    notes = models.CharField(max_length=300, blank=True)

    class Meta:
        ordering: ClassVar = ["due_date"]

    def __str__(self) -> str:
        return self.title

    @property
    def is_overdue(self) -> bool:
        return self.completed_on is None and self.due_date < timezone.localdate()


class ProjectDocument(TimeStampedModel):
    class Kind(models.TextChoices):
        DESIGN = "design", "Architectural / engineering design"
        BOQ = "boq", "Bill of quantities"
        PERMIT = "permit", "Permit / approval"
        CONTRACT = "contract", "Contract"
        REPORT = "report", "Report / feasibility study"
        OTHER = "other", "Other"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="documents")
    kind = models.CharField(max_length=10, choices=Kind.choices)
    title = models.CharField(max_length=200)
    issued_on = models.DateField(null=True, blank=True)
    file = PrivateFileField(upload_to=RandomUploadTo("projects"))

    class Meta:
        ordering: ClassVar = ["kind", "-issued_on"]

    def __str__(self) -> str:
        return self.title


class SiteVisit(TimeStampedModel):
    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="site_visits")
    date = models.DateField(default=timezone.localdate)
    visited_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    progress_percent = models.PositiveSmallIntegerField(
        validators=[MaxValueValidator(100)], help_text="Overall progress seen on site"
    )
    summary = models.TextField()
    quality_concerns = models.TextField(blank=True)

    class Meta:
        ordering: ClassVar = ["-date"]
        verbose_name = "site visit / progress log"

    def __str__(self) -> str:
        return f"Site visit {self.date:%d %b %Y} ({self.progress_percent}%)"


class SitePhoto(TimeStampedModel):
    visit = models.ForeignKey(SiteVisit, on_delete=models.CASCADE, related_name="photos")
    image = PrivateFileField(upload_to=RandomUploadTo("site"), images_only=True)
    caption = models.CharField(max_length=200, blank=True)

    def __str__(self) -> str:
        return self.caption or f"Site photo #{self.pk}"


class ProjectRisk(TimeStampedModel):
    class Kind(models.TextChoices):
        RISK = "risk", "Risk (may happen)"
        ISSUE = "issue", "Issue (happening now)"

    class Level(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"

    class Status(models.TextChoices):
        OPEN = "open", "Open"
        MITIGATED = "mitigated", "Being managed"
        CLOSED = "closed", "Closed"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="risks")
    kind = models.CharField(max_length=6, choices=Kind.choices, default=Kind.RISK)
    description = models.CharField(max_length=300)
    severity = models.CharField(max_length=6, choices=Level.choices, default=Level.MEDIUM)
    mitigation = models.TextField(blank=True)
    owner = models.CharField(max_length=150, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)

    class Meta:
        ordering: ClassVar = ["status", "-severity"]
        verbose_name = "risk or issue"

    def __str__(self) -> str:
        return f"{self.get_kind_display().split(' ')[0]}: {self.description}"


class MaintenanceRequest(TimeStampedModel):
    class Priority(models.TextChoices):
        LOW = "low", "Low"
        MEDIUM = "medium", "Medium"
        HIGH = "high", "High"
        URGENT = "urgent", "Urgent (safety)"

    class Status(models.TextChoices):
        OPEN = "open", "Reported"
        SCHEDULED = "scheduled", "Scheduled"
        IN_PROGRESS = "in_progress", "In progress"
        DONE = "done", "Done"

    OPEN_STATES = (Status.OPEN, Status.SCHEDULED, Status.IN_PROGRESS)

    site = models.ForeignKey(
        Property, on_delete=models.CASCADE, related_name="maintenance_requests", verbose_name="property"
    )
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    priority = models.CharField(max_length=8, choices=Priority.choices, default=Priority.MEDIUM)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.OPEN, db_index=True)
    reported_on = models.DateField(default=timezone.localdate)
    scheduled_for = models.DateField(null=True, blank=True)
    completed_on = models.DateField(null=True, blank=True)
    recurring_every_days = models.PositiveIntegerField(
        null=True, blank=True, help_text="For scheduled routine maintenance"
    )
    cost = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    assigned_to = models.CharField(max_length=150, blank=True)

    class Meta:
        ordering: ClassVar = ["status", "-priority", "reported_on"]

    def __str__(self) -> str:
        return f"{self.title} ({self.site})"


class CapitalProposal(TimeStampedModel):
    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        WITH_FINANCE = "with_finance", "Sent to Finance for fundraising"
        FUNDED = "funded", "Funded"
        DECLINED = "declined", "Not funded"

    project = models.ForeignKey(Project, on_delete=models.CASCADE, related_name="proposals")
    title = models.CharField(max_length=200)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    summary = models.TextField(help_text="Need, plan, cost and impact in plain language")
    document = PrivateFileField(upload_to=RandomUploadTo("capital"), blank=True)
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.DRAFT)
    finance_proposal = models.OneToOneField(
        "finance.Proposal",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="capital_proposal",
        editable=False,
    )

    class Meta:
        ordering: ClassVar = ["-created_at"]
        verbose_name = "capital project proposal"

    def __str__(self) -> str:
        return self.title
