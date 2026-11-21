"""Monthly performance targets (ministry decision 4): targets, change history, actuals, RAG, overdue, CSV import.

RAG rule (default, documented in the admin guide): Green = 90% of target or better, Amber = 70-89%,
Red = below 70%. For "lower is better" indicators the percentage is inverted before the same rule applies.
A month's actual is OVERDUE when it is still missing on the 10th day of the following month.
"""

from __future__ import annotations

import csv
import datetime as dt
import io
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.db.models import QuerySet
from django.http import HttpRequest
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from .access import Access
from .models import Department, Indicator, IndicatorValue, MonthlyTarget, TargetChange

GREEN, AMBER = 90, 70
GRACE_DAYS = 10
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"]
CSV_COLUMNS = [
    "category",
    "name",
    "unit",
    "department",
    "branch",
    "year",
    "annual_target",
    "higher_is_better",
    *MONTHS,
]


def max_csv_bytes() -> int:
    from core.upload_policy import get_policy

    return get_policy("csv_import").max_bytes


MAX_CSV_ROWS = 1000


def can_manage(access: Access) -> bool:
    """Leadership sets and adjusts targets: the Founder / Super Admin and Executive Leadership."""
    return access.is_super_admin or access.is_executive


def rag(progress: int | None) -> str:
    if progress is None:
        return ""
    if progress >= GREEN:
        return "green"
    return "amber" if progress >= AMBER else "red"


RAG_STATUS = {
    "green": ("good", "Green: on track"),
    "amber": ("warn", "Amber: behind"),
    "red": ("bad", "Red: off track"),
}


# ------------------------------------------------------------------------------------------------ targets
def ensure_monthly(indicator: Indicator) -> None:
    """Create the twelve monthly targets from the annual target if they do not exist yet."""
    existing = set(indicator.monthly_targets.values_list("month", flat=True))
    split = indicator.split_annual()
    MonthlyTarget.objects.bulk_create(
        [
            MonthlyTarget(indicator=indicator, month=m, target=split[m - 1])
            for m in range(1, 13)
            if m not in existing
        ]
    )


def _require(access: Access) -> None:
    if not can_manage(access):
        raise PermissionDenied("Only leadership sets or changes targets.")


def _reason(reason: str) -> str:
    reason = (reason or "").strip()
    if len(reason) < 5:
        raise ValidationError("Give a reason for the change (at least a few words).")
    return reason[:500]


@transaction.atomic
def set_annual(request: HttpRequest, access: Access, indicator: Indicator, new: Decimal, reason: str) -> None:
    """Change the annual target and split it again into monthly targets (each change is recorded)."""
    _require(access)
    reason = _reason(reason)
    if new < 0:
        raise ValidationError("A target cannot be negative.")
    old = indicator.annual_target
    if old == new:
        return
    indicator.annual_target = new
    indicator.save(update_fields=["annual_target", "updated_at"])
    TargetChange.objects.create(
        indicator=indicator, month=None, old_value=old, new_value=new, reason=reason, changed_by=request.user
    )
    indicator.monthly_targets.all().delete()
    ensure_monthly(indicator)
    log_event(
        AuditLog.Action.CHANGE,
        request=request,
        obj=indicator,
        extra={"target": "annual", "old": str(old), "new": str(new)},
    )


@transaction.atomic
def set_months(
    request: HttpRequest, access: Access, indicator: Indicator, targets: dict[int, Decimal], reason: str
) -> int:
    """Edit some monthly targets; returns how many changed. The annual target follows for counts and money."""
    _require(access)
    reason = _reason(reason)
    ensure_monthly(indicator)
    current = {t.month: t for t in indicator.monthly_targets.all()}
    changed = 0
    for month, new in sorted(targets.items()):
        if month not in current:
            raise ValidationError(f"Month {month} does not exist.")
        if new < 0:
            raise ValidationError("A target cannot be negative.")
        row = current[month]
        if row.target == new:
            continue
        TargetChange.objects.create(
            indicator=indicator,
            month=month,
            old_value=row.target,
            new_value=new,
            reason=reason,
            changed_by=request.user,
        )
        row.target = new
        row.save(update_fields=["target", "updated_at"])
        changed += 1
    if changed and indicator.is_cumulative:
        total = sum((t.target for t in current.values()), Decimal("0"))
        if total != indicator.annual_target:
            TargetChange.objects.create(
                indicator=indicator,
                month=None,
                old_value=indicator.annual_target,
                new_value=total,
                reason=f"Sum of monthly targets. {reason}"[:500],
                changed_by=request.user,
            )
            indicator.annual_target = total
            indicator.save(update_fields=["annual_target", "updated_at"])
    if changed:
        log_event(
            AuditLog.Action.CHANGE,
            request=request,
            obj=indicator,
            extra={"target": "monthly", "months": changed},
        )
    return changed


# ------------------------------------------------------------------------------------------------ status
@dataclass
class Row:
    indicator: Indicator
    month: int
    monthly_target: Decimal
    monthly_actual: Decimal | None
    ytd_target: Decimal
    ytd_actual: Decimal | None
    progress: int | None
    rag: str
    trend: list[Decimal | None] = field(default_factory=list)
    targets: list[Decimal] = field(default_factory=list)
    overdue: list[int] = field(default_factory=list)

    @property
    def rag_status(self) -> tuple[str, str]:
        return RAG_STATUS.get(self.rag, ("", "No actuals yet"))

    @property
    def overdue_labels(self) -> str:
        return ", ".join(MONTHS[m - 1].title() for m in self.overdue)


def overdue_months(indicator: Indicator, recorded: set[int], today: dt.date | None = None) -> list[int]:
    today = today or timezone.localdate()
    created = (
        indicator.created_at.date().replace(day=1) if indicator.created_at else dt.date(indicator.year, 1, 1)
    )
    out = []
    for month in range(1, 13):
        if month in recorded or dt.date(indicator.year, month, 1) < created:
            continue  # months before the target existed are not chased
        due = dt.date(indicator.year + (month == 12), month % 12 + 1, GRACE_DAYS)
        if today > due:
            out.append(month)
    return out


def status(indicator: Indicator, month: int, today: dt.date | None = None) -> Row:
    """Target vs actual for ``month`` and the year to date, with trend, RAG and overdue months."""
    targets_by_month = indicator.monthly_map()
    values = {
        v.period_start.month: v.value for v in indicator.values.all() if v.period_start.year == indicator.year
    }
    targets = [targets_by_month[m] for m in range(1, 13)]
    trend = [values.get(m) for m in range(1, 13)]
    upto = list(range(1, month + 1))
    recorded = [values[m] for m in upto if m in values]
    if indicator.is_cumulative:
        ytd_target = sum((targets_by_month[m] for m in upto), Decimal("0"))
        ytd_actual = sum(recorded, Decimal("0")) if recorded else None
    else:
        ytd_target = targets_by_month[month]
        ytd_actual = recorded[-1] if recorded else None  # a level: the latest month counts
    progress = indicator.progress(ytd_actual, ytd_target)
    return Row(
        indicator=indicator,
        month=month,
        monthly_target=targets_by_month[month],
        monthly_actual=values.get(month),
        ytd_target=ytd_target,
        ytd_actual=ytd_actual,
        progress=progress,
        rag=rag(progress),
        trend=trend,
        targets=targets,
        overdue=overdue_months(indicator, set(values), today),
    )


def reporting_month(year: int, today: dt.date | None = None) -> int:
    """The last month that should have an actual: last month in the current year, December for past years."""
    today = today or timezone.localdate()
    if year < today.year:
        return 12
    if year > today.year:
        return 1
    return max(1, today.month - 1)


def board(qs: QuerySet, year: int, month: int | None = None) -> dict[str, Any]:
    """All indicators of a year grouped by category, for the Executive Overview and the targets screen."""
    month = month or reporting_month(year)
    rows = [
        status(i, month)
        for i in qs.filter(year=year, is_active=True)
        .select_related("department", "branch")
        .prefetch_related("monthly_targets", "values")
    ]
    categories = []
    for code, label in Indicator.Category.choices:
        mine = [r for r in rows if r.indicator.category == code]
        categories.append(
            {
                "code": code,
                "label": label,
                "rows": mine,
                "green": sum(r.rag == "green" for r in mine),
                "amber": sum(r.rag == "amber" for r in mine),
                "red": sum(r.rag == "red" for r in mine),
                "overdue": sum(bool(r.overdue) for r in mine),
            }
        )
    return {
        "year": year,
        "month": month,
        "month_label": dt.date(year, month, 1).strftime("%B %Y"),
        "categories": categories,
        "overdue": [r for r in rows if r.overdue],
        "count": len(rows),
    }


# ------------------------------------------------------------------------------------------------ CSV import
@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    errors: list[str] = field(default_factory=list)
    preview: list[dict[str, Any]] = field(default_factory=list)


def _dec(raw: str, label: str, line: int, errors: list[str]) -> Decimal | None:
    raw = (raw or "").strip().replace(",", "")
    if not raw:
        return None
    try:
        value = Decimal(raw)
    except InvalidOperation:
        errors.append(f"Line {line}: {label} '{raw[:20]}' is not a number.")
        return None
    if value < 0 or value >= Decimal("1e12"):
        errors.append(f"Line {line}: {label} must be between 0 and 999,999,999,999.")
        return None
    return value


def parse_csv(data: bytes) -> tuple[list[dict[str, Any]], list[str]]:
    """Validate every row; return (clean rows, errors). Nothing is saved here."""
    from branches.models import Branch

    errors: list[str] = []
    if len(data) > max_csv_bytes():
        return [], [f"The file is larger than {max_csv_bytes() // 1024} KB."]
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        return [], ["Save the file as CSV (UTF-8)."]
    reader = csv.DictReader(io.StringIO(text))
    headers = [h.strip().lower() for h in (reader.fieldnames or [])]
    missing = [c for c in CSV_COLUMNS[:7] if c not in headers]
    if missing:
        return [], [f"Missing column(s): {', '.join(missing)}. Download the template for the exact columns."]
    departments = {d.code: d for d in Department.objects.all()}
    branches = {b.slug: b for b in Branch.objects.all()} | {b.name.lower(): b for b in Branch.objects.all()}
    categories = dict(Indicator.Category.choices)
    units = dict(Indicator.Unit.choices)
    rows: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for n, raw in enumerate(reader, start=2):
        if n - 1 > MAX_CSV_ROWS:
            errors.append(f"More than {MAX_CSV_ROWS} rows; split the file.")
            break
        row = {(k or "").strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        if not any(row.values()):
            continue
        before = len(errors)
        category = row.get("category", "").lower()
        if category not in categories:
            errors.append(f"Line {n}: category '{category[:30]}' is not one of: {', '.join(categories)}.")
        name = row.get("name", "")
        if not name or len(name) > 160:
            errors.append(f"Line {n}: name is required (up to 160 characters).")
        unit = row.get("unit", "").lower() or "number"
        if unit not in units:
            errors.append(f"Line {n}: unit must be number, percent or money.")
        dept = departments.get(row.get("department", "").lower())
        if dept is None:
            errors.append(f"Line {n}: department must be one of: {', '.join(departments)}.")
        branch_raw = row.get("branch", "")
        branch = None
        if branch_raw and branch_raw.lower() not in ("all", "all branches"):
            branch = branches.get(branch_raw.lower()) or branches.get(branch_raw)
            if branch is None:
                errors.append(
                    f"Line {n}: branch '{branch_raw[:40]}' not found (leave empty for all branches)."
                )
        year_raw = row.get("year", "")
        year = int(year_raw) if year_raw.isdigit() else 0
        if not 2000 <= year <= 2100:
            errors.append(f"Line {n}: year must be a four-digit financial year.")
        annual = _dec(row.get("annual_target", ""), "annual_target", n, errors)
        if annual is None and len(errors) == before:
            errors.append(f"Line {n}: annual_target is required.")
        higher_raw = row.get("higher_is_better", "").lower()
        if higher_raw not in ("", "yes", "no", "true", "false", "1", "0"):
            errors.append(f"Line {n}: higher_is_better must be yes or no.")
        months = {}
        for i, key in enumerate(MONTHS, start=1):
            value = _dec(row.get(key, ""), key, n, errors)
            if value is not None:
                months[i] = value
        if months and len(months) != 12:
            errors.append(f"Line {n}: give all twelve monthly targets or none (they are then split evenly).")
        if (
            months
            and annual is not None
            and unit != "percent"
            and len(months) == 12
            and sum(months.values(), Decimal("0")) != annual
        ):
            errors.append(f"Line {n}: the twelve monthly targets must add up to the annual target.")
        key = (dept.code if dept else "", name.lower(), year, branch.pk if branch else None)
        if key in seen:
            errors.append(f"Line {n}: the same indicator appears twice in the file.")
        seen.add(key)
        if len(errors) == before:
            rows.append(
                {
                    "line": n,
                    "category": category,
                    "name": name,
                    "unit": unit,
                    "department": dept,
                    "branch": branch,
                    "year": year,
                    "annual_target": annual,
                    "higher_is_better": higher_raw not in ("no", "false", "0"),
                    "months": months,
                }
            )
    if not rows and not errors:
        errors.append("The file has no rows.")
    return rows, errors


@transaction.atomic
def import_csv(request: HttpRequest, access: Access, data: bytes, *, dry_run: bool) -> ImportResult:
    """All or nothing: any invalid row means nothing is imported. Changes to existing targets are recorded."""
    _require(access)
    result = ImportResult()
    rows, result.errors = parse_csv(data)
    if result.errors:
        return result
    for row in rows:
        existing = Indicator.objects.filter(
            department=row["department"], name__iexact=row["name"], year=row["year"], branch=row["branch"]
        ).first()
        result.preview.append({**row, "action": "update" if existing else "create"})
    if dry_run:
        return result
    reason = "Imported from a targets file"
    for row in rows:
        indicator = Indicator.objects.filter(
            department=row["department"], name__iexact=row["name"], year=row["year"], branch=row["branch"]
        ).first()
        if indicator is None:
            indicator = Indicator.objects.create(
                department=row["department"],
                category=row["category"],
                name=row["name"],
                unit=row["unit"],
                year=row["year"],
                branch=row["branch"],
                annual_target=row["annual_target"],
                higher_is_better=row["higher_is_better"],
            )
            TargetChange.objects.create(
                indicator=indicator,
                old_value=None,
                new_value=row["annual_target"],
                reason=reason,
                changed_by=request.user,
            )
            result.created += 1
        else:
            indicator.category, indicator.unit = row["category"], row["unit"]
            indicator.higher_is_better = row["higher_is_better"]
            indicator.save(update_fields=["category", "unit", "higher_is_better", "updated_at"])
            set_annual(request, access, indicator, row["annual_target"], reason)
            result.updated += 1
        ensure_monthly(indicator)
        if row["months"]:
            set_months(request, access, indicator, row["months"], reason)
    log_event(
        AuditLog.Action.IMPORT,
        request=request,
        model=Indicator,
        extra={"created": result.created, "updated": result.updated},
    )
    return result


def template_csv() -> str:
    year = timezone.localdate().year
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(CSV_COLUMNS)
    writer.writerow(
        [
            "evangelism",
            "Souls won (example row: replace it)",
            "number",
            "missions",
            "",
            year,
            "1200",
            "yes",
            *([""] * 12),
        ]
    )
    return out.getvalue()


def record_actual(
    request: HttpRequest, indicator: Indicator, month: int, value: Decimal, note: str = ""
) -> IndicatorValue:
    start = dt.date(indicator.year, month, 1)
    obj, _created = IndicatorValue.objects.update_or_create(
        indicator=indicator,
        period_start=start,
        defaults={"value": value, "note": note[:300], "entered_by": request.user},
    )
    return obj
