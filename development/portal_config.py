"""Development & Infrastructure in the staff portal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from finance.models import BudgetLine, LedgerEntry
from portal.access import HEAD, MEMBER, Access
from portal.charts import Chart, grouped_counts, timeline
from portal.dashboards import KPI, Action, Dashboard, Filters, Item, dashboard, executive_summary, handoffs
from portal.models import Department
from portal.resources import DateInput, Resource, register

from .models import (
    CapitalProposal,
    Contractor,
    MaintenanceRequest,
    Milestone,
    Project,
    ProjectDocument,
    ProjectRisk,
    Property,
    SitePhoto,
    SiteVisit,
)

DEPT = "development"


class _Development(Resource):
    department = DEPT


class ProjectForm(forms.ModelForm):
    contractors = forms.ModelMultipleChoiceField(
        queryset=Contractor.objects.all(), required=False, widget=forms.CheckboxSelectMultiple
    )

    class Meta:
        model = Project
        fields = [
            "name",
            "kind",
            "phase",
            "branch",
            "site",
            "description",
            "budget_line",
            "funding_secured",
            "currency",
            "start_date",
            "target_end",
            "completed_on",
            "project_manager",
            "contractors",
        ]
        widgets = {"start_date": DateInput(), "target_end": DateInput(), "completed_on": DateInput()}


@register
class ProjectResource(_Development):
    model = Project
    slug = "projects"
    branch_lookup = "branch"
    label = "Project register"
    nav_group = "Projects"
    list_fields: ClassVar = [
        "name",
        "kind",
        "phase",
        "budget_display",
        "spent_display",
        "progress",
        "target_end",
    ]
    filters: ClassVar = ["phase", "kind", "branch"]
    search_fields: ClassVar = ["name"]
    form_class = ProjectForm
    fields: ClassVar = ProjectForm.Meta.fields
    detail_fields: ClassVar = [*ProjectForm.Meta.fields, "spent_display", "gap_display", "progress"]
    children: ClassVar = [
        ("milestones", "milestones", "Milestones"),
        ("site_visits", "site-visits", "Site visits and progress"),
        ("ledger_entries", "project-costs", "Costs (from the Finance ledger)"),
        ("documents", "project-documents", "Documents (designs, BOQs, permits, contracts)"),
        ("risks", "risks", "Risks and issues"),
        ("proposals", "capital-proposals", "Capital proposals"),
    ]
    perms: ClassVar = {"delete": HEAD}

    detail_template = "development/project_detail.html"
    fk_querysets: ClassVar = {
        "budget_line": lambda access: BudgetLine.objects.filter(department__code=DEPT),
    }

    def extra_context(self, request: HttpRequest, access: Access, obj: Model) -> dict[str, Any]:
        return {"money": obj.finance_summary()}  # type: ignore[attr-defined]

    def budget_display(self, obj: Project) -> str:
        return f"{obj.budget:,.2f}" if obj.budget_line_id else "No budget line"

    budget_display.short_description = "Budget"  # type: ignore[attr-defined]

    def spent_display(self, obj: Project) -> str:
        pct = f" ({int(obj.spent * 100 / obj.budget)}%)" if obj.budget else ""
        return f"{obj.spent:,.2f}{pct}"

    spent_display.short_description = "Spent"  # type: ignore[attr-defined]

    def gap_display(self, obj: Project) -> str:
        return f"{obj.funding_gap:,.2f}"

    gap_display.short_description = "Funding gap"  # type: ignore[attr-defined]

    def progress(self, obj: Project) -> str:
        value = obj.latest_progress
        return "—" if value is None else f"{value}%"

    progress.short_description = "Progress (last site visit)"  # type: ignore[attr-defined]


class _ProjectChild(_Development):
    nav = False
    parent_field = "project"


@register
class MilestoneResource(_ProjectChild):
    model = Milestone
    slug = "milestones"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["title", "due_date", "completed_on", "status_text"]
    fields: ClassVar = ["project", "title", "due_date", "completed_on", "notes"]

    def status_text(self, obj: Milestone) -> str:
        if obj.completed_on:
            return "Done"
        return "Overdue" if obj.is_overdue else "Upcoming"

    status_text.short_description = "Status"  # type: ignore[attr-defined]


@register
class ProjectCostResource(_ProjectChild):
    """Project costs ARE Finance ledger entries tagged with the project (decision 6): no second set of books.

    Development records a cost (a draft expenditure entry charged to the project's budget line) and submits it;
    it then follows executive approval like every expenditure. Development never sees receipts, payees or
    entries of other departments.
    """

    model = LedgerEntry
    slug = "project-costs"
    label = "Project costs (Finance ledger)"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["number", "date", "project", "description", "amount", "status", "unbudgeted"]
    fields: ClassVar = ["project", "date", "amount", "description", "reference"]
    detail_fields: ClassVar = [
        "number",
        "status",
        "project",
        "date",
        "amount",
        "description",
        "reference",
        "budget_line",
        "unbudgeted",
        "rejection_note",
        "posted_at",
    ]
    export_fields: ClassVar = ["number", "date", "project", "description", "amount", "status"]
    perms: ClassVar = {"delete": MEMBER, "change": MEMBER}
    fk_querysets: ClassVar = {"project": lambda access: Project.objects.all()}

    def get_form_class(self, access: Access, obj: Model | None = None) -> type[forms.ModelForm]:
        base = super().get_form_class(access, obj)

        class CostForm(base):  # type: ignore[valid-type, misc]
            def __init__(self, *args: Any, **kwargs: Any) -> None:
                super().__init__(*args, **kwargs)
                # Fixed parts of a project cost, set before validation so the ledger rules apply.
                self.instance.kind = LedgerEntry.Kind.EXPENSE
                self.instance.category = self.instance.category or "construction"
                self.instance.department = Department.objects.get(code=DEPT)

            def clean(self) -> dict[str, Any]:
                cleaned = super().clean()
                project = cleaned.get("project")
                if project is not None:
                    self.instance.budget_line = project.budget_line
                return cleaned

        return CostForm

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        return qs.filter(project__isnull=False, kind=LedgerEntry.Kind.EXPENSE)

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        if action in ("change", "delete"):
            entry: LedgerEntry = obj  # type: ignore[assignment]
            return (
                entry.status in ("draft", "rejected")
                and entry.department is not None
                and entry.department.code == DEPT  # never a draft Finance is preparing
                and (entry.recorded_by_id == access.user.pk or access.is_head(DEPT))
            )
        return True

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        super().before_save(request, access, obj, created)
        entry: LedgerEntry = obj  # type: ignore[assignment]
        entry.kind = LedgerEntry.Kind.EXPENSE
        entry.department = Department.objects.get(code=DEPT)
        entry.budget_line = entry.project.budget_line
        entry.branch = entry.project.branch
        entry.currency = entry.project.currency

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        entry: LedgerEntry = obj  # type: ignore[assignment]
        if entry.status in ("draft", "rejected") and self.object_allows(access, "change", entry):
            return [
                {
                    "label": "Submit for approval",
                    "url": reverse("portal:development:cost_submit", args=[entry.pk]),
                    "style": "primary",
                }
            ]
        return []


@register
class DocumentResource(_ProjectChild):
    model = ProjectDocument
    slug = "project-documents"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["title", "kind", "issued_on"]
    fields: ClassVar = ["project", "kind", "title", "issued_on", "file"]
    sensitive = True


@register
class SiteVisitResource(_ProjectChild):
    model = SiteVisit
    slug = "site-visits"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["date", "progress_percent", "visited_by"]
    fields: ClassVar = ["project", "date", "progress_percent", "summary", "quality_concerns"]
    children: ClassVar = [("photos", "site-photos", "Photos")]

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        super().before_save(request, access, obj, created)
        if created:
            obj.visited_by = request.user  # type: ignore[attr-defined]


@register
class SitePhotoResource(_Development):
    model = SitePhoto
    slug = "site-photos"
    branch_lookup = "visit__project__branch"
    nav = False
    parent_field = "visit"
    list_fields: ClassVar = ["caption", "created_at"]
    fields: ClassVar = ["visit", "image", "caption"]


@register
class RiskResource(_ProjectChild):
    model = ProjectRisk
    slug = "risks"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["description", "kind", "severity", "status", "owner"]
    filters: ClassVar = ["kind", "severity", "status"]
    fields: ClassVar = ["project", "kind", "description", "severity", "mitigation", "owner", "status"]


@register
class ProposalResource(_ProjectChild):
    model = CapitalProposal
    slug = "capital-proposals"
    branch_lookup = "project__branch"
    nav = True
    label = "Capital proposals"
    nav_group = "Projects"
    list_fields: ClassVar = ["title", "project", "amount", "status"]
    filters: ClassVar = ["status"]
    fields: ClassVar = ["project", "title", "amount", "summary", "document"]
    detail_fields: ClassVar = [
        "project",
        "title",
        "amount",
        "summary",
        "document",
        "status",
        "finance_proposal",
    ]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        if obj.status != CapitalProposal.Status.DRAFT or not access.is_head(DEPT):  # type: ignore[attr-defined]
            return []
        return [
            {
                "label": "Send to Finance for fundraising",
                "url": reverse("portal:development:send_to_finance", args=[obj.pk]),
                "style": "primary",
                "confirm": "Finance will see this proposal in its Appeals & proposals list.",
            }
        ]


@register
class PropertyResource(_Development):
    model = Property
    slug = "properties"
    branch_lookup = "branch"
    label = "Property & land register"
    nav_group = "Facilities"
    list_fields: ClassVar = ["name", "kind", "location", "tenure", "branch"]
    filters: ClassVar = ["kind", "tenure", "branch"]
    fields: ClassVar = [
        "name",
        "kind",
        "location",
        "branch",
        "size",
        "tenure",
        "title_reference",
        "acquired_on",
        "title_document",
        "notes",
    ]
    children: ClassVar = [
        ("maintenance_requests", "maintenance", "Maintenance"),
        ("projects", "projects", "Projects"),
    ]
    sensitive = True
    perms: ClassVar = {"delete": HEAD}


@register
class MaintenanceResource(_Development):
    model = MaintenanceRequest
    slug = "maintenance"
    branch_lookup = "site__branch"
    label = "Maintenance requests & schedule"
    nav_group = "Facilities"
    parent_field = "site"
    list_fields: ClassVar = ["title", "site", "priority", "status", "reported_on", "scheduled_for"]
    filters: ClassVar = ["status", "priority", "site"]
    fields: ClassVar = [
        "site",
        "title",
        "description",
        "priority",
        "status",
        "reported_on",
        "scheduled_for",
        "completed_on",
        "recurring_every_days",
        "cost",
        "assigned_to",
    ]
    date_field = "reported_on"


@register
class ContractorResource(_Development):
    model = Contractor
    slug = "contractors"
    label = "Contractors & partners"
    nav_group = "Facilities"
    list_fields: ClassVar = ["name", "kind", "specialty", "rating"]
    filters: ClassVar = ["kind", "rating"]
    search_fields: ClassVar = ["name", "specialty"]
    fields: ClassVar = ["name", "kind", "specialty", "contact_person", "phone", "email", "rating", "notes"]
    children: ClassVar = [("projects", "projects", "Projects")]


# ------------------------------------------------------------------------------------------ dashboard
@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    projects = (
        ProjectResource()
        .get_queryset(access)
        .select_related("budget_line")
        .prefetch_related("site_visits", "milestones")
    )
    if filters.branch_id:
        projects = projects.filter(branch_id=filters.branch_id)
    active = [p for p in projects if p.phase in Project.ACTIVE]
    today = timezone.localdate()
    overdue = Milestone.objects.filter(
        project__in=projects, completed_on__isnull=True, due_date__lt=today
    ).select_related("project")
    backlog = MaintenanceResource().get_queryset(access).filter(status__in=MaintenanceRequest.OPEN_STATES)
    if filters.branch_id:
        backlog = backlog.filter(site__branch_id=filters.branch_id)
    budget = sum((p.budget for p in active), Decimal("0"))
    spent = sum((p.spent for p in active), Decimal("0"))
    gap = sum((p.funding_gap for p in active), Decimal("0"))
    summaries = {p.pk: p.finance_summary() for p in active}
    committed = sum((m["committed"] for m in summaries.values()), Decimal("0"))
    purl = ProjectResource().url("list")
    kpis = [
        KPI("Active projects", len(active), url=purl, code="active_projects"),
        KPI("Budget (active)", f"{budget:,.2f}", code="budget"),
        KPI(
            "Spent (active)",
            f"{spent:,.2f}",
            f"{int(spent * 100 / budget) if budget else 0}% of budget",
            code="spent",
        ),
        KPI(
            "Committed (active)",
            f"{committed:,.2f}",
            "Awaiting approval, or approved and not yet paid",
            code="committed",
        ),
        KPI(
            "Funding gap",
            f"{gap:,.2f}",
            "Budget not yet secured",
            code="funding_gap",
            status="warn" if gap else "",
        ),
        KPI(
            "Milestones overdue",
            overdue.count(),
            code="milestones_overdue",
            status="bad" if overdue.exists() else "",
        ),
        KPI(
            "Maintenance backlog",
            backlog.count(),
            url=MaintenanceResource().url("list"),
            code="maintenance_backlog",
            status="bad" if backlog.filter(priority="urgent").exists() else "",
        ),
        KPI(
            "Open risks (high)",
            ProjectRisk.objects.filter(project__in=projects, status="open", severity="high").count(),
            code="high_risks",
        ),
    ]
    charts = [
        Chart("Projects by stage", "hbar", grouped_counts(projects, "phase", dict(Project.Phase.choices))),
        Chart(
            "Budget spent per active project (%)",
            "hbar",
            [(p.name, summaries[p.pk]["spent_pct"] or 0) for p in active],
            unit="%",
        ),
    ]
    rows = []
    for p in active:
        if not (p.start_date and p.target_end):
            continue
        late = (
            p.target_end < today
            or Milestone.objects.filter(project=p, completed_on__isnull=True, due_date__lt=today).exists()
        )
        rows.append(
            {
                "label": p.name,
                "start": p.start_date,
                "end": p.target_end,
                "progress": p.latest_progress,
                "url": ProjectResource().url("detail", p),
                "late": late,
            }
        )
    sections = [
        {
            "title": "Budget vs spent per project (from the Finance ledger)",
            "columns": [
                "Project",
                "Stage",
                "Budget",
                "Committed",
                "Spent",
                "Remaining",
                "Money spent",
                "Milestones done",
            ],
            "rows": [
                [
                    p.name,
                    p.get_phase_display(),
                    f"{m['budget']:,.2f}" if not m["no_budget_line"] else "No budget line",
                    f"{m['committed']:,.2f}",
                    f"{m['spent']:,.2f}",
                    f"{m['remaining']:,.2f}",
                    "—" if m["spent_pct"] is None else f"{m['spent_pct']}%",
                    "—" if m["milestones_pct"] is None else f"{m['milestones_pct']}%",
                ]
                for p in active
                for m in [summaries[p.pk]]
            ],
            "empty": "No active projects.",
        }
    ]
    attention = [
        Item(
            f"Overspent: {p}",
            f"Spent {summaries[p.pk]['spent']:,.2f} of {summaries[p.pk]['budget']:,.2f}",
            ProjectResource().url("detail", p),
            "bad",
        )
        for p in active
        if summaries[p.pk]["overspent"]
    ]
    attention += [
        Item(
            f"UNBUDGETED costs on {p}: {summaries[p.pk]['unbudgeted']}",
            "Need an executive justification",
            ProjectResource().url("detail", p),
            "bad",
        )
        for p in active
        if summaries[p.pk]["unbudgeted"]
    ]
    attention += [
        Item(
            f"Money ahead of progress: {p}",
            f"{summaries[p.pk]['spent_pct']}% spent, {summaries[p.pk]['milestones_pct']}% of milestones done",
            ProjectResource().url("detail", p),
            "warn",
        )
        for p in active
        if summaries[p.pk]["spent_pct"] is not None
        and summaries[p.pk]["milestones_pct"] is not None
        and summaries[p.pk]["spent_pct"] > summaries[p.pk]["milestones_pct"] + 20
    ]
    attention += [
        Item(
            f"No budget line: {p}",
            "Ask Finance for a cost centre",
            ProjectResource().url("detail", p),
            "warn",
        )
        for p in active
        if summaries[p.pk]["no_budget_line"]
    ]
    attention += [
        Item(
            f"Overdue milestone: {m.title}",
            f"{m.project} · due {m.due_date:%d %b}",
            ProjectResource().url("detail", m.project),
            "bad",
        )
        for m in overdue[:6]
    ]
    attention += [
        Item(
            f"Urgent maintenance: {r}",
            r.reported_on.strftime("%d %b"),
            MaintenanceResource().url("detail", r),
            "bad",
        )
        for r in backlog.filter(priority="urgent")[:5]
    ]
    stale = [
        p
        for p in active
        if p.phase == Project.Phase.CONSTRUCTION
        and (not p.site_visits.exists() or p.site_visits.first().date < today - timedelta(days=30))
    ]
    attention += [
        Item(f"No site visit in 30 days: {p}", "", ProjectResource().url("detail", p), "warn")
        for p in stale[:5]
    ]
    activity = [
        Item(str(v), str(v.project), SiteVisitResource().url("detail", v))
        for v in SiteVisit.objects.filter(project__in=projects)[:6]
    ]
    actions = [
        Action("New project", ProjectResource().url("create"), primary=True),
        Action("Log a site visit", SiteVisitResource().url("create")),
        Action("Report maintenance", MaintenanceResource().url("create")),
    ]
    return Dashboard(
        title="Development & Infrastructure",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
        sections=sections,
        timeline=timeline(rows),
        timeline_title="Project timeline",
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    active = list(Project.objects.filter(phase__in=Project.ACTIVE))
    gap = sum((p.funding_gap for p in active), Decimal("0"))
    overdue = Milestone.objects.filter(completed_on__isnull=True, due_date__lt=timezone.localdate()).count()
    return [
        KPI("Active projects", len(active)),
        KPI("Funding gap", f"{gap:,.2f}"),
        KPI("Milestones overdue", overdue, status="bad" if overdue else ""),
        KPI(
            "Maintenance backlog",
            MaintenanceRequest.objects.filter(status__in=MaintenanceRequest.OPEN_STATES).count(),
        ),
    ]


@handoffs
def capital_handoffs() -> list[Item]:
    count = CapitalProposal.objects.filter(status=CapitalProposal.Status.WITH_FINANCE).count()
    if not count:
        return []
    return [Item(f"Development → Finance: {count} capital proposal(s) for fundraising", "", "", "")]
