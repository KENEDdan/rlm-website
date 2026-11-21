"""Departments, who belongs to them, and the shared monitoring & evaluation (M&E) layer."""

from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal
from typing import Any, ClassVar

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models
from django.utils import timezone

from core.models import TimeStampedModel


class Department(TimeStampedModel):
    """One of the seven ministry departments. Codes are fixed (each has its own dashboard); names editable."""

    class Code(models.TextChoices):
        MEMBERSHIP = "membership", "Membership Administration"
        FINANCE = "finance", "Finance & Resource Mobilization"
        LOGISTICS = "logistics", "Logistics & Procurement"
        MEDIA = "media", "Media & Communications"
        MISSIONS = "missions", "Missions & Outreach"
        DISCIPLESHIP = "discipleship", "Discipleship"
        DEVELOPMENT = "development", "Development & Infrastructure"

    code = models.CharField(max_length=20, choices=Code.choices, unique=True)
    name = models.CharField(max_length=120, unique=True)
    purpose = models.TextField(blank=True, help_text="Primary responsibility, shown on the dashboard.")
    order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering: ClassVar = ["order", "name"]

    def __str__(self) -> str:
        return self.name


class DepartmentMembership(TimeStampedModel):
    """A user's place in a department. Writable ONLY through accounts.services (Super Admin)."""

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="memberships")
    is_head = models.BooleanField(default=False, help_text="Department head: approvals, exports, reports.")
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="department_memberships",
        help_text="Scope of this role: empty = all branches (department leaders); a branch = only that branch's "
        "records in this department (a Branch Coordinator who also serves here).",
    )

    class Meta:
        ordering: ClassVar = ["department__order", "-is_head"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["user", "department"], name="unique_department_membership")
        ]

    def __str__(self) -> str:
        role = "head" if self.is_head else "member"
        return f"{self.department} ({role}, {self.scope_label})"

    @property
    def scope_label(self) -> str:
        return f"{self.branch} only" if self.branch_id else "all branches"

    @property
    def audit_label(self) -> str:
        return f"department membership #{self.pk}"


# ---------------------------------------------------------------------------------------------- M&E layer
class Period(models.TextChoices):
    MONTHLY = "monthly", "Monthly"
    QUARTERLY = "quarterly", "Quarterly"
    ANNUAL = "annual", "Annual"


def period_start(day: date, period: str) -> date:
    if period == Period.MONTHLY:
        return day.replace(day=1)
    if period == Period.QUARTERLY:
        return day.replace(month=((day.month - 1) // 3) * 3 + 1, day=1)
    return day.replace(month=1, day=1)


def period_end(start: date, period: str) -> date:
    months = {Period.MONTHLY: 1, Period.QUARTERLY: 3, Period.ANNUAL: 12}[Period(period)]
    month_index = start.month - 1 + months
    nxt = date(start.year + month_index // 12, month_index % 12 + 1, 1)
    return date.fromordinal(nxt.toordinal() - 1)


class Indicator(TimeStampedModel):
    """A performance target for one financial year (ministry decision 4).

    The annual target is split into twelve monthly targets (editable); departments record monthly actuals as
    ``IndicatorValue`` rows. Every change to a target is kept in ``TargetChange`` (who, old, new, reason).
    """

    class Unit(models.TextChoices):
        NUMBER = "number", "Number"
        PERCENT = "percent", "Percent"
        MONEY = "money", "Money"

    class Category(models.TextChoices):
        EVANGELISM = "evangelism", "Evangelism"
        DISCIPLESHIP = "discipleship", "Discipleship"
        YOUTH = "youth", "Youth fellowships"
        MEMBERSHIP = "membership", "Membership"
        PARTNERSHIPS = "partnerships", "Partnerships"
        MISSIONS = "missions", "Missions"
        FINANCE = "finance", "Finance"
        DEVELOPMENT = "development", "Development"
        MEDIA = "media", "Media"
        PRAYER = "prayer", "Prayer"

    department = models.ForeignKey(
        Department, on_delete=models.CASCADE, related_name="indicators", verbose_name="owner department"
    )
    category = models.CharField(max_length=20, choices=Category.choices, db_index=True)
    name = models.CharField(max_length=160)
    description = models.TextField(blank=True)
    unit = models.CharField(max_length=10, choices=Unit.choices, default=Unit.NUMBER)
    year = models.PositiveSmallIntegerField(
        "financial year", db_index=True, help_text="January to December (ministry decision 2)."
    )
    activity = models.ForeignKey(
        "programs.Activity",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="indicators",
        help_text="Optional: the ministry activity this target measures (e.g. Monthly Youth Revival Fellowship).",
    )
    branch = models.ForeignKey(
        "branches.Branch",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="indicators",
        help_text="Leave empty for a ministry-wide target.",
    )
    annual_target = models.DecimalField(max_digits=14, decimal_places=2)
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.MONTHLY, editable=False)
    higher_is_better = models.BooleanField(default=True)
    auto_source = models.CharField(
        max_length=60,
        blank=True,
        help_text="Optional: the code of a dashboard figure that fills this value automatically "
        "when a report is generated (listed in the admin guide).",
    )
    is_demo = models.BooleanField(
        default=False,
        editable=False,
        help_text="Sample target created for demonstration; never a real target.",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering: ClassVar = ["category", "department__order", "name"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["department", "name", "year", "branch"],
                name="unique_indicator_per_year_branch",
                nulls_distinct=False,
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.year})"

    @property
    def is_cumulative(self) -> bool:
        """Counts and money add up over the year; percentages are a level to hold every month."""
        return self.unit != self.Unit.PERCENT

    def split_annual(self) -> list[Decimal]:
        """Twelve monthly targets: an even split (rounding goes to December) or, for percentages, the same level."""
        if not self.is_cumulative:
            return [self.annual_target] * 12
        each = (self.annual_target / 12).quantize(Decimal("0.01"), rounding=ROUND_DOWN)
        return [each] * 11 + [self.annual_target - each * 11]

    def monthly_map(self) -> dict[int, Decimal]:
        stored = {t.month: t.target for t in self.monthly_targets.all()}
        if len(stored) == 12:
            return stored
        split = self.split_annual()
        return {m: stored.get(m, split[m - 1]) for m in range(1, 13)}

    def target_for(self, start: date, period: str | None = None) -> Decimal:
        """Target for the period beginning ``start`` (a month, quarter or the whole year)."""
        months = {Period.MONTHLY: 1, Period.QUARTERLY: 3, Period.ANNUAL: 12}[Period(period or self.period)]
        targets = self.monthly_map()
        chosen = [targets[m] for m in range(start.month, min(12, start.month + months - 1) + 1)]
        if not chosen:
            return Decimal("0")
        return sum(chosen, Decimal("0")) if self.is_cumulative else sum(chosen, Decimal("0")) / len(chosen)

    # kept for older screens/reports that read ``indicator.target``: the monthly target of the current month
    @property
    def target(self) -> Decimal:
        today = timezone.localdate()
        month = today.month if today.year == self.year else 1
        return self.monthly_map()[month]

    def latest_value(self) -> IndicatorValue | None:
        return self.values.order_by("-period_start").first()

    def progress(self, value: Decimal | None, target: Decimal | None = None) -> int | None:
        """Percent of target reached (uncapped, so over-achievement shows); lower-is-better is inverted."""
        target = self.target if target is None else target
        if value is None:
            return None
        if not target:
            return None if self.higher_is_better else (100 if value <= 0 else 0)
        if self.higher_is_better:
            return max(0, int(value * 100 / target))
        if value <= target:
            return 100
        return max(0, int(target * 100 / value))


class MonthlyTarget(TimeStampedModel):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="monthly_targets")
    month = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(12)])
    target = models.DecimalField(max_digits=14, decimal_places=2)

    class Meta:
        ordering: ClassVar = ["month"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["indicator", "month"], name="unique_month_target")
        ]

    def __str__(self) -> str:
        return f"{self.indicator} month {self.month}: {self.target}"


class TargetChange(models.Model):
    """Append-only history of target changes (who, old, new, reason). Never edited or deleted."""

    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="target_changes")
    month = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Empty = the annual target.")
    old_value = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    new_value = models.DecimalField(max_digits=14, decimal_places=2)
    reason = models.CharField(max_length=500)
    changed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+"
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering: ClassVar = ["-created_at"]

    def __str__(self) -> str:
        which = "annual" if self.month is None else f"month {self.month}"
        return f"{self.indicator} {which}: {self.old_value} -> {self.new_value}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk:
            raise PermissionError("Target history cannot be changed.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise PermissionError("Target history cannot be deleted.")


class IndicatorValue(TimeStampedModel):
    indicator = models.ForeignKey(Indicator, on_delete=models.CASCADE, related_name="values")
    period_start = models.DateField(help_text="First day of the month/quarter/year this value is for.")
    value = models.DecimalField(max_digits=14, decimal_places=2)
    note = models.CharField(max_length=300, blank=True)
    entered_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )

    class Meta:
        ordering: ClassVar = ["-period_start"]
        constraints: ClassVar = [
            models.UniqueConstraint(fields=["indicator", "period_start"], name="unique_indicator_period")
        ]

    def __str__(self) -> str:
        return f"{self.indicator} {self.period_start:%b %Y}: {self.value}"

    def clean(self) -> None:
        if self.indicator_id and self.period_start:
            expected = period_start(self.period_start, self.indicator.period)
            if expected != self.period_start:
                raise ValidationError(
                    {"period_start": f"Use the first day of the period ({expected:%d %b %Y})."}
                )

    @property
    def target(self) -> Decimal:
        return self.indicator.target_for(self.period_start)

    @property
    def progress(self) -> int | None:
        return self.indicator.progress(self.value, self.target)


class DepartmentReport(TimeStampedModel):
    """Monthly/quarterly report: generated from the dashboard, completed by the department, reviewed by the Founder."""

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SUBMITTED = "submitted", "Submitted"
        RETURNED = "returned", "Returned for changes"
        REVIEWED = "reviewed", "Reviewed by the Founder"

    department = models.ForeignKey(Department, on_delete=models.CASCADE, related_name="reports")
    period = models.CharField(max_length=10, choices=Period.choices, default=Period.MONTHLY)
    period_start = models.DateField()
    period_end = models.DateField(editable=False)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT, db_index=True)
    figures = models.JSONField(default=list, blank=True, editable=False)
    indicators = models.JSONField(default=list, blank=True, editable=False)
    highlights = models.TextField(blank=True, help_text="What went well, with numbers where possible.")
    challenges = models.TextField(blank=True)
    plans_next_period = models.TextField(blank=True)
    support_needed = models.TextField(blank=True, help_text="Decisions or help needed from leadership.")
    prepared_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, related_name="+", editable=False
    )
    submitted_at = models.DateTimeField(null=True, blank=True, editable=False)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
        editable=False,
    )
    reviewed_at = models.DateTimeField(null=True, blank=True, editable=False)
    review_comment = models.TextField(blank=True, editable=False)

    class Meta:
        ordering: ClassVar = ["-period_start", "department__order"]
        constraints: ClassVar = [
            models.UniqueConstraint(
                fields=["department", "period", "period_start"], name="unique_department_report"
            )
        ]

    def __str__(self) -> str:
        return f"{self.department} - {self.period_label}"

    @property
    def period_label(self) -> str:
        if self.period == Period.MONTHLY:
            return f"{self.period_start:%B %Y}"
        if self.period == Period.QUARTERLY:
            return f"Q{(self.period_start.month - 1) // 3 + 1} {self.period_start.year}"
        return str(self.period_start.year)

    def save(self, *args: Any, **kwargs: Any) -> None:
        self.period_start = period_start(self.period_start, self.period)
        self.period_end = period_end(self.period_start, self.period)
        super().save(*args, **kwargs)

    @property
    def financial_year(self) -> int:
        """Financial year = calendar year (ministry decision 2)."""
        return self.period_start.year

    @property
    def is_editable(self) -> bool:
        return self.status in (self.Status.DRAFT, self.Status.RETURNED)

    @property
    def due_date(self) -> date:
        day = getattr(settings, "REPORT_DUE_DAY", 10)
        nxt = date.fromordinal(self.period_end.toordinal() + 1)
        return nxt.replace(day=min(day, 28))

    @property
    def is_overdue(self) -> bool:
        return self.is_editable and timezone.localdate() > self.due_date
