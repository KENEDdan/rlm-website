"""Development & Infrastructure in the staff portal."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.db.models import Model
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from portal.access import HEAD, Access
from portal.charts import Chart, grouped_counts, timeline
from portal.dashboards import KPI, Action, Dashboard, Filters, Item, dashboard, executive_summary, handoffs
from portal.resources import DateInput, Resource, register

from .models import (
    CapitalProposal,
    Contractor,
    MaintenanceRequest,
    Milestone,
    Project,
    ProjectDocument,
    ProjectExpense,
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
            "budget",
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
    list_fields: ClassVar = ["name", "kind", "phase", "budget", "spent_display", "progress", "target_end"]
    filters: ClassVar = ["phase", "kind", "branch"]
    search_fields: ClassVar = ["name"]
    form_class = ProjectForm
    fields: ClassVar = ProjectForm.Meta.fields
    detail_fields: ClassVar = [*ProjectForm.Meta.fields, "spent_display", "gap_display", "progress"]
    children: ClassVar = [
        ("milestones", "milestones", "Milestones"),
        ("site_visits", "site-visits", "Site visits and progress"),
        ("expenses", "project-costs", "Costs"),
        ("documents", "project-documents", "Documents (designs, BOQs, permits, contracts)"),
        ("risks", "risks", "Risks and issues"),
        ("proposals", "capital-proposals", "Capital proposals"),
    ]
    perms: ClassVar = {"delete": HEAD}

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
class ExpenseResource(_ProjectChild):
    model = ProjectExpense
    slug = "project-costs"
    branch_lookup = "project__branch"
    list_fields: ClassVar = ["date", "description", "amount", "reference"]
    fields: ClassVar = ["project", "date", "description", "amount", "reference"]


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
    projects = ProjectResource().get_queryset(access).prefetch_related("expenses", "site_visits")
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
            [(p.name, int(p.spent * 100 / p.budget) if p.budget else 0) for p in active],
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
            "title": "Budget vs spent per project",
            "columns": ["Project", "Stage", "Budget", "Spent", "Funding secured", "Gap"],
            "rows": [
                [
                    p.name,
                    p.get_phase_display(),
                    f"{p.budget:,.2f}",
                    f"{p.spent:,.2f}",
                    f"{p.funding_secured:,.2f}",
                    f"{p.funding_gap:,.2f}",
                ]
                for p in active
            ],
            "empty": "No active projects.",
        }
    ]
    attention = [
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
