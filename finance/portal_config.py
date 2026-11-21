"""Finance & Resource Mobilization in the staff portal (the most restricted department)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, ClassVar

from django.db.models import Model, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from contact.models import ContactMessage
from core.retention import RetentionColumns
from giving.models import Donation, PartnershipEnquiry
from portal.access import FOUNDER, HEAD, MEMBER, Access
from portal.charts import Chart, monthly_series
from portal.dashboards import (
    KPI,
    Action,
    Dashboard,
    Filters,
    Item,
    dashboard,
    executive_summary,
    pending_approvals,
)
from portal.resources import Resource, register

from . import services
from .models import (
    ApprovalDecision,
    Approver,
    BudgetLine,
    Donor,
    FinanceSettings,
    FinanceVolunteer,
    FinancialYear,
    GrantOpportunity,
    IncomeSource,
    LedgerEntry,
    Pledge,
    Proposal,
)

DEPT = "finance"
E = LedgerEntry.Status


def money(value: Decimal | None) -> str:
    return f"{(value or Decimal('0')):,.2f}"


def _step(
    name: str, pk: int, label: str, *, style: str = "", method: str = "post", confirm: str = ""
) -> dict[str, Any]:
    return {
        "label": label,
        "url": reverse("portal:finance:ledger_step", args=[pk, name]),
        "style": style,
        "method": method,
        "confirm": confirm,
    }


def _all(label: str) -> Any:
    """Dropdown of every record of another app's model (Finance tags payments with what they paid for)."""
    from django.apps import apps

    return lambda access: apps.get_model(label).objects.all()


class _Finance(Resource):
    department = DEPT
    sensitive = True


@register
class LedgerResource(_Finance):
    model = LedgerEntry
    slug = "ledger"
    branch_lookup = "branch"
    label = "Income & expenditure ledger"
    nav_group = "Accounts"
    icon = "ledger"
    description = (
        "Record, then submit. Someone other than the recorder approves and posts. Posted entries cannot be "
        "changed: use 'Reverse' to correct them."
    )
    list_fields: ClassVar = ["number", "date", "kind", "description", "department", "amount", "status"]
    filters: ClassVar = ["kind", "status", "department", "category", "income_source"]
    search_fields: ClassVar = ["number", "reference", "description"]
    fields: ClassVar = [
        "kind",
        "date",
        "amount",
        "currency",
        "department",
        "branch",
        "budget_line",
        "category",
        "income_source",
        "description",
        "counterparty",
        "reference",
        "receipt",
        "project",
        "purchase_order",
        "campaign",
        "logistics_plan",
    ]
    detail_fields: ClassVar = [
        "number",
        "status",
        *fields,
        "recorded_by",
        "submitted_at",
        "approved_by",
        "posted_at",
        "rejection_note",
        "reverses",
        "unbudgeted",
    ]
    export_fields: ClassVar = [
        "number",
        "date",
        "kind",
        "status",
        "amount",
        "currency",
        "department",
        "category",
        "income_source",
        "description",
        "reference",
    ]
    date_field = "date"
    perms: ClassVar = {"view": MEMBER, "add": MEMBER, "change": MEMBER, "delete": MEMBER, "export": HEAD}

    fk_querysets: ClassVar = {
        # Finance links a payment to what it was for (decision 6); these lists show labels only.
        "project": _all("development.Project"),
        "purchase_order": _all("logistics.PurchaseOrder"),
        "campaign": _all("missions.Campaign"),
        "logistics_plan": _all("logistics.LogisticsPlan"),
    }

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        entry: LedgerEntry = obj  # type: ignore[assignment]
        if action in ("change", "delete"):
            editable = entry.status in (E.DRAFT, E.REJECTED) and not entry.is_reversal
            return editable and (entry.recorded_by_id == access.user.pk or access.is_head(DEPT))
        return True

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        entry: LedgerEntry = obj  # type: ignore[assignment]
        out = []
        if entry.status in (E.DRAFT, E.REJECTED) and (
            entry.recorded_by_id == access.user.pk or access.is_head(DEPT)
        ):
            out.append(_step("submit", entry.pk, "Submit for approval", style="primary"))
        if entry.status == E.SUBMITTED and entry.kind == LedgerEntry.Kind.EXPENSE:
            from .approvals import KINDS, is_approver

            if is_approver(access.user) and entry.recorded_by_id != access.user.pk:
                out.append(
                    {
                        "label": "Review for executive approval",
                        "url": KINDS["expense"].detail_url(entry),
                        "method": "get",
                        "style": "primary",
                    }
                )
        if entry.status == E.SUBMITTED and entry.kind == LedgerEntry.Kind.INCOME:
            allowed, _reason = services.can_approve(access.user, entry)
            if allowed:
                out.append(
                    _step(
                        "approve",
                        entry.pk,
                        "Approve and post",
                        style="primary",
                        confirm="Approve and post this entry? Posted entries can only be corrected by reversal.",
                    )
                )
            if entry.recorded_by_id != access.user.pk:
                out.append(_step("reject", entry.pk, "Reject", method="get"))
        reversible = entry.status == E.POSTED and not entry.is_reversal and access.is_head(DEPT)
        if reversible and not LedgerEntry.objects.filter(reverses=entry).exists():
            out.append(_step("reverse", entry.pk, "Reverse (correct)", method="get"))
        return out


@register
class BudgetResource(_Finance):
    model = BudgetLine
    slug = "budget"
    branch_lookup = "branch"
    label = "Annual budget"
    nav_group = "Accounts"
    sensitive = False
    list_fields: ClassVar = ["year", "department", "branch", "name", "amount", "status", "spent", "remaining"]
    filters: ClassVar = ["department", "category", "status"]
    search_fields: ClassVar = ["name"]
    fields: ClassVar = ["year", "department", "branch", "category", "name", "amount", "notes"]
    ordering: ClassVar = ["-year", "department__order", "name"]
    perms: ClassVar = {"add": HEAD, "change": HEAD, "delete": HEAD}

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        if action in ("change", "delete"):
            return obj.status in (BudgetLine.Status.DRAFT, BudgetLine.Status.REJECTED)  # type: ignore[attr-defined]
        return True

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        line: BudgetLine = obj  # type: ignore[assignment]
        if access.is_head(DEPT) and line.status in (BudgetLine.Status.DRAFT, BudgetLine.Status.REJECTED):
            return [
                {
                    "label": "Submit for executive approval",
                    "url": reverse("portal:finance:budget_line_submit", args=[line.pk]),
                    "style": "primary",
                }
            ]
        return []

    def remaining(self, obj: BudgetLine) -> str:
        from .approvals import line_position

        return money(line_position(obj).remaining)

    remaining.short_description = "Remaining (after commitments)"  # type: ignore[attr-defined]

    def spent(self, obj: BudgetLine) -> str:
        total = obj.entries.filter(status=E.POSTED).aggregate(t=Sum("amount"))["t"]
        return money(total)

    spent.short_description = "Spent (posted)"  # type: ignore[attr-defined]


@register
class DonationResource(_Finance):
    model = Donation
    slug = "donations"
    label = "Website donations & pledges"
    nav_group = "Giving"
    list_fields: ClassVar = ["__str__", "amount", "currency", "status", "provider", "given_on", "created_at"]
    filters: ClassVar = ["status", "provider", "category"]
    detail_fields: ClassVar = [
        "amount",
        "currency",
        "status",
        "provider",
        "category",
        "given_on",
        "donor_name",
        "donor_email",
        "donor_phone",
        "transfer_reference",
        "is_anonymous",
        "receipt_number",
        "confirmed_by",
        "confirmed_at",
    ]
    date_field = "created_at"
    perms: ClassVar = {"add": FOUNDER + 1, "change": FOUNDER + 1, "delete": FOUNDER + 1, "export": HEAD}

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        if obj.status in (Donation.Status.PLEDGED, Donation.Status.PENDING):  # type: ignore[attr-defined]
            return [
                {
                    "label": "Confirm received",
                    "url": reverse("portal:finance:donation_confirm", args=[obj.pk]),
                    "style": "primary",
                    "confirm": "Confirm the money arrived? An income entry is created for someone else to approve.",
                }
            ]
        return []


@register
class EnquiryResource(RetentionColumns, _Finance):
    model = PartnershipEnquiry
    slug = "partner-registrations"
    label = "Partnership registrations"
    nav_group = "Resource mobilization"
    list_fields: ClassVar = ["__str__", "partner_type", "country", "status", "created_at"]
    filters: ClassVar = ["status"]
    detail_fields: ClassVar = [
        "partner_type",
        "name",
        "organisation",
        "email",
        "phone",
        "country",
        "message",
        "status",
        "outcome",
        "retention_deadline",
        "record_reference",
    ]
    date_field = "created_at"
    perms: ClassVar = {"add": FOUNDER + 1, "change": FOUNDER + 1, "delete": HEAD, "export": HEAD}

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        out = []
        if obj.outcome == "pending" and access.is_head(DEPT):  # type: ignore[attr-defined]
            out += [
                {
                    "label": "Taken forward: partner pipeline",
                    "url": reverse("portal:finance:enquiry_outcome", args=[obj.pk, "successful"]),
                    "style": "primary",
                    "confirm": "Mark as successful? The registration keeps only a reference; the partner record keeps "
                    "the details.",
                },
                {
                    "label": "Not taken forward",
                    "url": reverse("portal:finance:enquiry_outcome", args=[obj.pk, "unsuccessful"]),
                    "confirm": "Mark as unsuccessful? It will be deleted after the retention period.",
                },
            ]
        return out + self._pipeline_actions(obj)

    def _pipeline_actions(self, obj: Model) -> list[dict[str, Any]]:
        if Donor.objects.filter(source_enquiry=obj).exists():
            donor = Donor.objects.get(source_enquiry=obj)
            return [
                {
                    "label": "Open in donor pipeline",
                    "url": DonorResource().url("detail", donor),
                    "method": "get",
                }
            ]
        return [
            {
                "label": "Add to donor pipeline",
                "url": reverse("portal:finance:enquiry_to_donor", args=[obj.pk]),
                "style": "primary",
            }
        ]


@register
class FinanceEnquiryResource(_Finance):
    """Contact-form messages about giving, finance or partnership: ONLY Finance (and the Super Admin) see them."""

    model = ContactMessage
    slug = "enquiries"
    label = "Giving and partnership enquiries"
    label_singular = "Enquiry"
    nav_group = "Resource mobilization"
    list_fields: ClassVar = ["__str__", "category", "status", "created_at"]
    filters: ClassVar = ["status", "category"]
    detail_fields: ClassVar = [
        "category",
        "name",
        "email",
        "phone",
        "subject",
        "message",
        "status",
        "internal_notes",
    ]
    fields: ClassVar = ["status", "internal_notes"]
    date_field = "created_at"
    perms: ClassVar = {"add": FOUNDER + 1, "delete": HEAD, "export": HEAD}

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        return qs.finance_queue()

    def covers(self, obj: Model) -> bool:
        return bool(getattr(obj, "is_finance_queue", False))


@register
class DonorResource(_Finance):
    model = Donor
    slug = "donors"
    label = "Donors, sponsors & partners"
    nav_group = "Resource mobilization"
    list_fields: ClassVar = ["name", "kind", "stage", "country", "owner", "next_step_due"]
    filters: ClassVar = ["kind", "stage", "owner"]
    fields: ClassVar = [
        "kind",
        "name",
        "contact_person",
        "email",
        "phone",
        "country",
        "city",
        "stage",
        "owner",
        "next_step",
        "next_step_due",
        "notes",
    ]
    export_fields: ClassVar = [
        "kind",
        "name",
        "contact_person",
        "email",
        "phone",
        "country",
        "stage",
        "next_step_due",
    ]
    children: ClassVar = [
        ("pledges", "pledges", "Pledges"),
        ("proposals", "proposals", "Appeals & proposals"),
        ("grants", "grants", "Grant opportunities"),
    ]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        return [
            {
                "label": "Accountability report",
                "url": reverse("portal:finance:donor_report", args=[obj.pk]),
                "method": "get",
            }
        ]


@register
class PledgeResource(_Finance):
    model = Pledge
    slug = "pledges"
    nav_group = "Resource mobilization"
    parent_field = "donor"
    list_fields: ClassVar = ["__str__", "donor", "purpose", "expected_by", "received_amount", "status"]
    filters: ClassVar = ["status"]
    fields: ClassVar = [
        "donor",
        "amount",
        "currency",
        "purpose",
        "pledged_on",
        "expected_by",
        "received_amount",
        "status",
    ]
    date_field = "pledged_on"


@register
class GrantResource(_Finance):
    model = GrantOpportunity
    slug = "grants"
    label = "Grant opportunities"
    nav_group = "Resource mobilization"
    sensitive = False
    list_fields: ClassVar = ["title", "funder", "amount", "deadline", "status", "owner"]
    filters: ClassVar = ["status", "owner"]
    fields: ClassVar = [
        "funder",
        "title",
        "amount",
        "currency",
        "deadline",
        "status",
        "owner",
        "link",
        "donor",
        "notes",
    ]
    date_field = "deadline"
    ordering: ClassVar = ["deadline"]


@register
class ProposalResource(_Finance):
    model = Proposal
    slug = "proposals"
    label = "Appeals & proposals"
    nav_group = "Resource mobilization"
    sensitive = False
    list_fields: ClassVar = ["title", "kind", "donor", "amount_requested", "status", "sent_on"]
    filters: ClassVar = ["kind", "status"]
    fields: ClassVar = [
        "kind",
        "title",
        "donor",
        "grant",
        "amount_requested",
        "status",
        "sent_on",
        "document",
        "notes",
    ]
    date_field = "sent_on"


@register
class VolunteerResource(RetentionColumns, _Finance):
    model = FinanceVolunteer
    slug = "volunteers"
    label = "Finance volunteers (vetting)"
    nav_group = "People"
    description = (
        "Applications from the website. Approval here never gives anyone access: only the Super Admin can."
    )
    list_fields: ClassVar = [
        "__str__",
        "status",
        "education_level",
        "finance_experience",
        "references_checked",
        "created_at",
    ]
    filters: ClassVar = ["status", "finance_experience", "references_checked"]
    fields: ClassVar = ["references_checked", "vetting_notes"]
    detail_fields: ClassVar = [
        "outcome",
        "retention_deadline",
        "record_reference",
        "status",
        "full_name",
        "gender",
        "nationality",
        "country",
        "city",
        "phone",
        "email",
        "occupation",
        "education_level",
        "field_of_study",
        "finance_experience",
        "computer_skills",
        "statement",
        "willing_integrity",
        "declaration",
        "references_checked",
        "vetting_notes",
        "decided_at",
    ]
    date_field = "created_at"
    perms: ClassVar = {"add": FOUNDER + 1, "change": MEMBER, "delete": HEAD, "export": HEAD}

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        labels = {
            "references": "Start reference check",
            "interview": "Move to interview",
            "approve": "Approve volunteer",
            "decline": "Do not take forward",
        }
        out = []
        for step, (sources, _target) in services.VOLUNTEER_STEPS.items():
            if obj.status in sources and (step not in ("approve", "decline") or access.is_head(DEPT)):  # type: ignore[attr-defined]
                out.append(
                    {
                        "label": labels[step],
                        "url": reverse("portal:finance:volunteer_step", args=[obj.pk, step]),
                        "style": "primary" if step == "approve" else ("danger" if step == "decline" else ""),
                    }
                )
        return out


@register
class SettingsResource(_Finance):
    model = FinanceSettings
    slug = "settings"
    label = "Finance settings"
    nav_group = "Accounts"
    sensitive = False
    list_fields: ClassVar = ["currency", "unbudgeted_requires_adjustment"]
    fields: ClassVar = ["currency", "unbudgeted_requires_adjustment"]
    perms: ClassVar = {
        "view": HEAD,
        "add": FOUNDER + 1,
        "change": HEAD,
        "delete": FOUNDER + 1,
        "export": FOUNDER + 1,
    }

    def get_queryset(self, access: Access) -> QuerySet:
        FinanceSettings.load()
        return super().get_queryset(access)


@register
class ApproverResource(_Finance):
    """Who gives executive approval. Super Admin only, with re-authentication for every change."""

    model = Approver
    slug = "approvers"
    label = "Executive approvers"
    nav_group = "Accounts"
    sensitive = False
    reauth_required = True
    description = (
        "The Founder, the Executive Director and, when the Founder is away, an acting approver with start and end "
        "dates. If this list is empty the Super Admins approve."
    )
    list_fields: ClassVar = ["user", "role", "starts_on", "ends_on", "is_active"]
    filters: ClassVar = ["role", "is_active"]
    fields: ClassVar = ["user", "role", "starts_on", "ends_on", "is_active"]
    perms: ClassVar = {
        "view": FOUNDER,
        "add": FOUNDER,
        "change": FOUNDER,
        "delete": FOUNDER + 1,
        "export": FOUNDER,
    }


@register
class DecisionResource(_Finance):
    """Permanent record of every executive decision (read-only)."""

    model = ApprovalDecision
    slug = "approval-decisions"
    label = "Approval decisions"
    nav_group = "Accounts"
    sensitive = False
    list_fields: ClassVar = [
        "created_at",
        "reference",
        "kind",
        "decision",
        "unbudgeted",
        "override",
        "amount",
        "approver",
    ]
    filters: ClassVar = ["decision", "unbudgeted", "override", "kind"]
    detail_fields: ClassVar = [*list_fields, "department", "justification", "approver_role"]
    perms: ClassVar = {
        "view": HEAD,
        "add": FOUNDER + 1,
        "change": FOUNDER + 1,
        "delete": FOUNDER + 1,
        "export": HEAD,
    }


@register
class FinancialYearResource(_Finance):
    model = FinancialYear
    slug = "financial-years"
    label = "Financial years"
    nav_group = "Accounts"
    sensitive = False
    description = "1 January to 31 December for every branch and department. A closed year accepts no new or changed entries."
    list_fields: ClassVar = ["year", "status", "closed_at", "closed_by", "reopened_at"]
    filters: ClassVar = ["status"]
    fields: ClassVar = ["year", "notes"]
    detail_fields: ClassVar = [
        "year",
        "status",
        "closed_at",
        "closed_by",
        "reopened_at",
        "reopened_by",
        "notes",
    ]
    perms: ClassVar = {
        "view": MEMBER,
        "add": HEAD,
        "change": FOUNDER + 1,
        "delete": FOUNDER + 1,
        "export": HEAD,
    }

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        fy: FinancialYear = obj  # type: ignore[assignment]
        if not fy.is_closed and access.is_head(DEPT):
            return [
                {
                    "label": "Close this year",
                    "url": reverse("portal:finance:year_close", args=[fy.pk]),
                    "style": "danger",
                    "confirm": f"Close {fy}? Nothing can then be recorded, changed or posted in it.",
                }
            ]
        if fy.is_closed and access.is_super_admin:
            return [
                {
                    "label": "Reopen this year",
                    "url": reverse("portal:finance:year_reopen", args=[fy.pk]),
                    "method": "get",
                }
            ]
        return []


# ------------------------------------------------------------------------------------------ dashboard
@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    ledger = LedgerResource().get_queryset(access)
    period = ledger.filter(date__gte=filters.start, date__lte=filters.end)
    in_period = services.totals(period)
    all_time = services.totals(ledger)
    year = filters.end.year
    budget_rows = services.budget_vs_actual(year, lines=BudgetResource().get_queryset(access), entries=ledger)
    total_budget = sum((r["budget"] for r in budget_rows), Decimal("0"))
    total_actual = sum((r["actual"] for r in budget_rows), Decimal("0"))
    burn = services.burn_rate()
    cash = all_time["net"]
    months_of_cash = f"{cash / burn:.1f} months" if burn > 0 else "—"
    pledges = (
        PledgeResource()
        .get_queryset(access)
        .exclude(status__in=[Pledge.Status.FULFILLED, Pledge.Status.CANCELLED])
    )
    outstanding = sum((p.outstanding for p in pledges), Decimal("0"))
    awaiting = ledger.filter(status=E.SUBMITTED)
    today = timezone.localdate()
    deadlines = (
        GrantResource()
        .get_queryset(access)
        .filter(
            deadline__gte=today,
            deadline__lte=today + timedelta(days=30),
            status__in=[GrantOpportunity.Status.IDENTIFIED, GrantOpportunity.Status.DRAFTING],
        )
    )
    lurl = LedgerResource().url("list")
    from .approvals import pending_items

    waiting = [] if access.branch_restricted_in(DEPT) else pending_items()
    unbudgeted = [i for i in waiting if i["unbudgeted"]]
    kpis = [
        KPI(
            "UNBUDGETED awaiting approval",
            f"{len(unbudgeted)} · {money(sum((i['amount'] for i in unbudgeted), Decimal('0')))}",
            "No approved budget line, or more than its remaining balance",
            reverse("portal:finance:approvals"),
            code="unbudgeted_waiting",
            status="bad" if unbudgeted else "",
        ),
        KPI(
            "Waiting for executive approval",
            len(waiting),
            url=reverse("portal:finance:approvals"),
            code="executive_waiting",
        ),
        KPI(
            "Income (period)",
            money(in_period["income"]),
            url=f"{lurl}?kind=income&status=posted",
            code="income",
        ),
        KPI(
            "Expenditure (period)",
            money(in_period["expense"]),
            url=f"{lurl}?kind=expense&status=posted",
            code="expense",
        ),
        KPI(
            "Net (period)", money(in_period["net"]), code="net", status="bad" if in_period["net"] < 0 else ""
        ),
        KPI("Cash position", money(cash), "All posted income minus expenditure", code="cash_position"),
        KPI(
            "Burn rate",
            money(burn),
            f"Average monthly spend, last 3 months · cash covers {months_of_cash}",
            code="burn_rate",
        ),
        KPI(
            f"Budget used {year}",
            f"{int(total_actual * 100 / total_budget) if total_budget else 0}%",
            f"{money(total_actual)} of {money(total_budget)}",
            BudgetResource().url("list"),
            code="budget_used_percent",
        ),
        KPI(
            "Outstanding pledges",
            money(outstanding),
            url=PledgeResource().url("list"),
            code="outstanding_pledges",
        ),
        KPI(
            "Awaiting approval",
            awaiting.count(),
            url=f"{lurl}?status=submitted",
            code="awaiting_approval",
            status="warn" if awaiting.exists() else "",
        ),
        KPI(
            "Grant deadlines (30 days)",
            deadlines.count(),
            url=GrantResource().url("list"),
            code="grant_deadlines",
        ),
    ]
    posted = ledger.filter(status=E.POSTED)
    sources = dict(IncomeSource.choices)
    by_source = (
        period.filter(status=E.POSTED, kind=LedgerEntry.Kind.INCOME)
        .values_list("income_source")
        .annotate(t=Sum("amount"))
        .order_by("-t")
    )
    charts = [
        Chart(
            "Income per month",
            "bar",
            monthly_series(
                posted.filter(kind="income"), "date", filters.start, filters.end, sum_field="amount"
            ),
        ),
        Chart(
            "Expenditure per month",
            "bar",
            monthly_series(
                posted.filter(kind="expense"), "date", filters.start, filters.end, sum_field="amount"
            ),
        ),
        Chart("Income by source (period)", "hbar", [(sources.get(k, k or "Other"), v) for k, v in by_source]),
        Chart(
            f"Budget used by department, {year} (%)",
            "hbar",
            [(r["label"], r["percent"] or 0) for r in budget_rows if r["budget"]],
            unit="%",
        ),
    ]
    attention = [
        Item(f"UNBUDGETED: {i['reference']} ({money(i['amount'])})", i["reason"], i["url"], "bad")
        for i in unbudgeted[:6]
    ]
    attention += [
        Item(f"Approve: {e}", e.description, LedgerResource().url("detail", e), "warn")
        for e in awaiting.exclude(recorded_by=access.user)[:6]
    ]
    attention += [
        Item(
            f"Grant deadline {g.deadline:%d %b}: {g.title}",
            g.funder,
            GrantResource().url("detail", g),
            "warn",
        )
        for g in deadlines[:5]
    ]
    attention += [
        Item(f"Pledge overdue: {p}", str(p.donor), PledgeResource().url("detail", p), "bad")
        for p in pledges.filter(expected_by__lt=today)[:5]
    ]
    unconfirmed = (
        DonationResource()
        .get_queryset(access)
        .filter(status=Donation.Status.PLEDGED, created_at__lt=timezone.now() - timedelta(days=7))
    )
    if unconfirmed.exists():
        attention.append(
            Item(
                f"{unconfirmed.count()} website pledge(s) unconfirmed for over a week",
                "",
                DonationResource().url("list") + "?status=pledged",
                "warn",
            )
        )
    for row in budget_rows:
        if row["percent"] and row["percent"] > 90:
            attention.append(
                Item(
                    f"{row['label']} has used {row['percent']}% of its {year} budget",
                    "",
                    BudgetResource().url("list"),
                    "bad",
                )
            )
    activity = [
        Item(str(e), f"{e.get_status_display()} · {e.date:%d %b}", LedgerResource().url("detail", e))
        for e in ledger.order_by("-updated_at")[:6]
    ]
    sections = [
        {
            "title": f"Budget vs actual by department, {year}",
            "columns": ["Department", "Budget", "Actual", "Remaining", "% used"],
            "rows": [
                [
                    r["label"],
                    money(r["budget"]),
                    money(r["actual"]),
                    money(r["remaining"]),
                    f"{r['percent']}%" if r["percent"] is not None else "—",
                ]
                for r in budget_rows
            ],
        }
    ]
    actions = [
        Action("Record income/expense", LedgerResource().url("create"), primary=True),
        Action("Awaiting approval", f"{lurl}?status=submitted"),
        Action("Donor pipeline", DonorResource().url("list")),
    ]
    return Dashboard(
        title="Finance & Resource Mobilization",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
        sections=sections,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    period = services.totals(LedgerEntry.objects.filter(date__gte=filters.start, date__lte=filters.end))
    cash = services.totals(LedgerEntry.objects.all())["net"]
    pledges = Pledge.objects.exclude(status__in=[Pledge.Status.FULFILLED, Pledge.Status.CANCELLED])
    return [
        KPI("Income (period)", money(period["income"])),
        KPI("Expenditure (period)", money(period["expense"])),
        KPI("Cash position", money(cash), status="bad" if cash < 0 else ""),
        KPI("Outstanding pledges", money(sum((p.outstanding for p in pledges), Decimal("0")))),
    ]


@pending_approvals(DEPT)
def pending() -> list[Item]:
    items = []
    awaiting = LedgerEntry.objects.filter(status=E.SUBMITTED).count()
    if awaiting:
        items.append(
            Item(
                f"{awaiting} ledger entr{'y' if awaiting == 1 else 'ies'} awaiting approval",
                "Finance",
                LedgerResource().url("list") + "?status=submitted",
                "warn",
            )
        )
    donations = Donation.objects.filter(status=Donation.Status.PLEDGED).count()
    if donations:
        items.append(
            Item(
                f"{donations} website pledge(s) to confirm",
                "Finance",
                DonationResource().url("list") + "?status=pledged",
                "warn",
            )
        )
    from .approvals import pending_items

    waiting = pending_items()
    if waiting:
        flagged = sum(1 for i in waiting if i["unbudgeted"])
        items.append(
            Item(
                f"{len(waiting)} item(s) waiting for executive approval"
                + (f", {flagged} UNBUDGETED" if flagged else ""),
                "Founder / Executive Director",
                reverse("portal:finance:approvals"),
                "bad" if flagged else "warn",
            )
        )
    vetting = FinanceVolunteer.objects.filter(status__in=["submitted", "references", "interview"]).count()
    if vetting:
        items.append(
            Item(
                f"{vetting} finance volunteer(s) being vetted", "Finance", VolunteerResource().url("list"), ""
            )
        )
    return items
