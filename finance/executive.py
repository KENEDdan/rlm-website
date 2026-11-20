"""Executive Finance page (ministry decision 1): ministry-wide SUMMARIES only.

Everything here is an aggregate (sums and counts). No query in this module returns a ledger line, donor,
voucher, receipt, payee or description; drill-down stops at category totals. Ledger detail stays with Finance
and the Founder.
"""

from __future__ import annotations

import datetime as dt
from collections import defaultdict
from decimal import Decimal
from typing import Any

from django.db.models import Q, QuerySet, Sum

from branches.models import Branch
from portal.charts import Chart
from portal.dashboards import Filters
from portal.models import Department

from .approvals import line_position, pending_items
from .models import BudgetLine, Category, IncomeSource, LedgerEntry, Pledge

ZERO = Decimal("0")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _sum(qs: QuerySet) -> Decimal:
    return qs.aggregate(t=Sum("amount"))["t"] or ZERO


def _posted(branch_id: int | None) -> QuerySet:
    qs = LedgerEntry.objects.filter(status=LedgerEntry.Status.POSTED)
    return qs.filter(branch_id=branch_id) if branch_id else qs


def _lines(year: int, branch_id: int | None) -> QuerySet:
    qs = BudgetLine.objects.filter(year=year, status=BudgetLine.Status.APPROVED).select_related("department")
    return qs.filter(branch_id=branch_id) if branch_id else qs


def summary(filters: Filters, department_code: str = "") -> dict[str, Any]:
    year = filters.fy or filters.end.year
    branch_id = filters.branch_id
    posted = _posted(branch_id)
    in_period = posted.filter(date__gte=filters.start, date__lte=filters.end)
    income_qs = in_period.filter(kind=LedgerEntry.Kind.INCOME)
    expense_qs = in_period.filter(kind=LedgerEntry.Kind.EXPENSE)
    income, expenditure = _sum(income_qs), _sum(expense_qs)
    to_date = posted.filter(date__lte=filters.end)
    cash = _sum(to_date.filter(kind=LedgerEntry.Kind.INCOME)) - _sum(
        to_date.filter(kind=LedgerEntry.Kind.EXPENSE)
    )

    pledges = Pledge.objects.filter(status__in=[Pledge.Status.OPEN, Pledge.Status.PARTIAL])
    outstanding = sum((p.outstanding for p in pledges.only("amount", "received_amount", "status")), ZERO)

    lines = list(_lines(year, branch_id))
    positions = {line.pk: line_position(line) for line in lines}
    approved_budget = sum((positions[line.pk].total for line in lines), ZERO)

    # budget vs actual by department (approved budget for the year; actual = posted spending in the period)
    budget_by_dept: dict[str, Decimal] = defaultdict(lambda: ZERO)
    names: dict[str, str] = {}
    for line in lines:
        budget_by_dept[line.department.code] += positions[line.pk].total
        names[line.department.code] = line.department.name
    actual_by_dept: dict[str, Decimal] = {}
    for code, name, total in expense_qs.values_list("department__code", "department__name").annotate(
        t=Sum("amount")
    ):
        actual_by_dept[code or ""] = total
        names.setdefault(code or "", name or "No department")
    by_department = [
        _row(names[c], budget_by_dept.get(c, ZERO), actual_by_dept.get(c, ZERO), code=c) for c in names
    ]

    # by branch (lines and spending without a branch are ministry-wide)
    branch_names = dict(Branch.objects.values_list("pk", "name"))
    budget_by_branch: dict[int | None, Decimal] = defaultdict(lambda: ZERO)
    for line in lines:
        budget_by_branch[line.branch_id] += positions[line.pk].total
    actual_by_branch = dict(expense_qs.values_list("branch_id").annotate(t=Sum("amount")))
    keys = sorted(
        set(budget_by_branch) | set(actual_by_branch), key=lambda k: (k is None, branch_names.get(k, ""))
    )
    by_branch = [
        _row(
            branch_names.get(k, "Ministry-wide (no branch)"),
            budget_by_branch.get(k, ZERO),
            actual_by_branch.get(k) or ZERO,
        )
        for k in keys
    ]

    # monthly trend for the financial year
    year_posted = posted.filter(date__year=year)
    monthly_in = {d.month: t for d, t in _by_month(year_posted.filter(kind=LedgerEntry.Kind.INCOME))}
    monthly_out = {d.month: t for d, t in _by_month(year_posted.filter(kind=LedgerEntry.Kind.EXPENSE))}
    months = [
        {"label": MONTHS[m - 1], "income": monthly_in.get(m, ZERO), "expenditure": monthly_out.get(m, ZERO)}
        for m in range(1, 13)
    ]

    waiting = pending_items()
    drill = None
    if department_code and department_code in names:
        drill = _drill(
            department_code,
            names[department_code],
            expense_qs,
            income_qs,
            [ln for ln in lines if ln.department.code == department_code],
            positions,
        )
    return {
        "year": year,
        "income": income,
        "expenditure": expenditure,
        "net": income - expenditure,
        "cash": cash,
        "outstanding_pledges": outstanding,
        "open_pledges": pledges.count(),
        "approved_budget": approved_budget,
        "budget_used_pct": (
            int(_sum(posted.filter(date__year=year, kind=LedgerEntry.Kind.EXPENSE)) * 100 / approved_budget)
            if approved_budget
            else None
        ),
        "by_department": by_department,
        "by_branch": by_branch,
        "months": months,
        "income_by_source": _totals(income_qs, "income_source", dict(IncomeSource.choices)),
        "waiting": len(waiting),
        "waiting_unbudgeted": sum(1 for i in waiting if i["unbudgeted"]),
        "unbudgeted_spent": _sum(expense_qs.filter(unbudgeted=True)),
        "drill": drill,
        "charts": [
            Chart("Income by month", "bar", [(m["label"], m["income"]) for m in months]),
            Chart("Expenditure by month", "bar", [(m["label"], m["expenditure"]) for m in months]),
        ],
    }


def _row(label: str, budget: Decimal, actual: Decimal, code: str = "") -> dict[str, Any]:
    return {
        "label": label,
        "code": code,
        "budget": budget,
        "actual": actual,
        "remaining": budget - actual,
        "percent": int(actual * 100 / budget) if budget else None,
        "over": actual > budget,
    }


def _by_month(qs: QuerySet) -> list[tuple[dt.date, Decimal]]:
    from django.db.models.functions import TruncMonth

    return list(
        qs.annotate(m=TruncMonth("date")).values_list("m").annotate(t=Sum("amount")).values_list("m", "t")
    )


def _totals(qs: QuerySet, field: str, labels: dict[str, str]) -> list[tuple[str, Decimal]]:
    rows = qs.values_list(field).annotate(t=Sum("amount")).order_by("-t")
    return [(labels.get(key, "Other") if key else "Not set", total) for key, total in rows]


def _drill(
    code: str,
    name: str,
    expense_qs: QuerySet,
    income_qs: QuerySet,
    lines: list[BudgetLine],
    positions: dict[int, Any],
) -> dict[str, Any]:
    """One department: category totals only (never entries)."""
    cats = dict(Category.choices)
    spend = expense_qs.filter(Q(department__code=code))
    budget_by_cat: dict[str, Decimal] = defaultdict(lambda: ZERO)
    for line in lines:
        budget_by_cat[line.category] += positions[line.pk].total
    actual_by_cat = dict(spend.values_list("category").annotate(t=Sum("amount")))
    keys = sorted(set(budget_by_cat) | set(actual_by_cat))
    return {
        "department": name,
        "code": code,
        "rows": [
            _row(cats.get(k, "Other"), budget_by_cat.get(k, ZERO), actual_by_cat.get(k) or ZERO) for k in keys
        ],
        "income": _sum(income_qs.filter(department__code=code)),
    }


def can_view(access: Any) -> bool:
    """Executive Leadership, the Founder/Super Admin and Finance."""
    return access.is_executive or access.is_super_admin or access.level("finance") >= 2


def departments() -> list[Department]:
    return list(Department.objects.all())
