"""Missions & Outreach in the staff portal."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django import forms
from django.db.models import Count, Model, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from finance.models import BudgetLine
from portal.access import HEAD, Access
from portal.charts import Chart, grouped_counts, monthly_series
from portal.dashboards import KPI, Action, Dashboard, Filters, Item, dashboard, executive_summary
from portal.resources import Resource, register

from .models import (
    Campaign,
    Community,
    CommunityContact,
    FieldPhoto,
    FieldReport,
    NewConvert,
    Team,
    TeamMember,
)

DEPT = "missions"


class _Missions(Resource):
    department = DEPT
    minor_lookup: str | None = None

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        if self.minor_lookup and not access.is_head(DEPT):
            qs = qs.exclude(**{self.minor_lookup: True})
        return qs


@register
class CampaignResource(_Missions):
    model = Campaign
    slug = "campaigns"
    label = "Outreach campaigns"
    nav_group = "Outreach"
    list_fields: ClassVar = [
        "title",
        "kind",
        "start_date",
        "location",
        "branch",
        "status",
        "reached",
        "decisions_total",
    ]
    filters: ClassVar = ["kind", "activity", "status", "branch", "team"]
    search_fields: ClassVar = ["title", "location"]
    fields: ClassVar = [
        "title",
        "kind",
        "activity",
        "community",
        "location",
        "branch",
        "start_date",
        "end_date",
        "team",
        "coordinator",
        "objectives",
        "budget_request",
        "budget_line",
        "materials",
        "status",
    ]
    detail_fields: ClassVar = [
        "title",
        "kind",
        "activity",
        "community",
        "location",
        "branch",
        "start_date",
        "end_date",
        "team",
        "coordinator",
        "objectives",
        "budget_request",
        "budget_line",
        "budget_status",
        "budget_unbudgeted",
        "budget_decision_note",
        "materials",
        "status",
        "spent",
    ]
    fk_querysets: ClassVar = {
        "budget_line": lambda access: BudgetLine.objects.filter(
            department__code=DEPT, status=BudgetLine.Status.APPROVED
        ),
    }

    def spent(self, obj: Campaign) -> str:
        from finance.approvals import _paid

        return f"{_paid(obj.ledger_entries.all()):,.2f}"

    spent.short_description = "Spent (posted in the Finance ledger)"  # type: ignore[attr-defined]

    def get_form_class(self, access: Access, obj: Model | None = None):  # type: ignore[no-untyped-def]
        base = super().get_form_class(access, obj)

        class CampaignForm(base):  # type: ignore[valid-type, misc]
            def clean(self) -> dict[str, Any]:
                cleaned = super().clean()
                needs = cleaned.get("budget_request")
                approved = self.instance.budget_is_approved if self.instance.pk else False
                if (
                    needs
                    and not approved
                    and cleaned.get("status") in ("approved", "in_progress", "completed")
                ):
                    self.add_error(
                        "status",
                        "This campaign has a budget: it can only go ahead once the budget is approved.",
                    )
                return cleaned

        return CampaignForm

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        campaign: Campaign = obj  # type: ignore[assignment]
        if (
            self.can(access, "change", campaign)
            and campaign.budget_request
            and campaign.budget_status in ("not_submitted", "rejected")
        ):
            return [
                {
                    "label": "Submit budget for executive approval",
                    "url": reverse("portal:missions:budget_submit", args=[campaign.pk]),
                    "style": "primary",
                }
            ]
        return []

    children: ClassVar = [
        ("reports", "field-reports", "Field reports"),
        ("converts", "converts", "New converts"),
    ]
    date_field = "start_date"
    branch_lookup = "branch"
    perms: ClassVar = {"delete": HEAD}

    def reached(self, obj: Campaign) -> int:
        return obj.reports.aggregate(t=Sum("souls_reached"))["t"] or 0

    reached.short_description = "Reached"  # type: ignore[attr-defined]

    def decisions_total(self, obj: Campaign) -> int:
        return obj.reports.aggregate(t=Sum("decisions"))["t"] or 0

    decisions_total.short_description = "Decisions"  # type: ignore[attr-defined]


@register
class ReportResource(_Missions):
    model = FieldReport
    slug = "field-reports"
    label = "Field reports"
    nav_group = "Outreach"
    parent_field = "campaign"
    list_fields: ClassVar = ["report_date", "campaign", "souls_reached", "decisions"]
    fields: ClassVar = ["campaign", "report_date", "souls_reached", "decisions", "challenges", "testimonies"]
    children: ClassVar = [("photos", "field-photos", "Photos")]
    date_field = "report_date"
    branch_lookup = "campaign__branch"
    branch_actions: ClassVar = {"view", "add", "change"}
    sensitive = True


@register
class PhotoResource(_Missions):
    model = FieldPhoto
    slug = "field-photos"
    nav = False
    parent_field = "report"
    list_fields: ClassVar = ["caption", "people_consented", "created_at"]
    fields: ClassVar = ["report", "image", "caption", "people_consented"]
    branch_lookup = "report__campaign__branch"
    branch_actions: ClassVar = {"view", "add"}


class ConvertForm(forms.ModelForm):
    class Meta:
        model = NewConvert
        fields = [
            "campaign",
            "decision_date",
            "full_name",
            "phone",
            "gender",
            "age_band",
            "location",
            "branch",
            "consent_to_contact",
            "guardian_contact",
            "notes",
        ]
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("age_band") == "under_18" and not cleaned.get("guardian_contact"):
            self.add_error("guardian_contact", "Under 18: record a parent or guardian contact.")
        return cleaned


@register
class ConvertResource(_Missions):
    model = NewConvert
    slug = "converts"
    label = "New converts"
    nav_group = "Outreach"
    description = "Every person recorded here is handed to Discipleship for follow-up automatically."
    list_fields: ClassVar = ["__str__", "decision_date", "campaign", "location", "age_band", "follow_up"]
    filters: ClassVar = ["gender", "age_band", "branch", "consent_to_contact"]
    form_class = ConvertForm
    fields: ClassVar = ConvertForm.Meta.fields
    detail_fields: ClassVar = [*ConvertForm.Meta.fields, "follow_up"]
    parent_field = "campaign"
    date_field = "decision_date"
    branch_lookup = "branch"
    branch_actions: ClassVar = {"view", "add"}
    minor_lookup = "is_minor"
    sensitive = True

    def follow_up(self, obj: NewConvert) -> str:
        follow = getattr(obj, "follow_up", None)
        return follow.get_status_display() if follow else "Not handed over"

    follow_up.short_description = "Discipleship follow-up"  # type: ignore[attr-defined]


@register
class CommunityResource(_Missions):
    model = Community
    slug = "communities"
    label = "Communities & locations"
    nav_group = "Field"
    list_fields: ClassVar = ["name", "kind", "region", "status", "opportunity", "branch"]
    filters: ClassVar = ["kind", "status", "opportunity", "branch"]
    search_fields: ClassVar = ["name", "region", "location"]
    fields: ClassVar = [
        "name",
        "kind",
        "country",
        "region",
        "location",
        "branch",
        "status",
        "opportunity",
        "population",
        "notes",
    ]
    children: ClassVar = [("contacts", "contacts", "Contacts"), ("campaigns", "campaigns", "Campaigns")]
    branch_lookup = "branch"


@register
class ContactResource(_Missions):
    model = CommunityContact
    slug = "contacts"
    nav = False
    parent_field = "community"
    list_fields: ClassVar = ["role", "name", "church_or_office"]
    fields: ClassVar = ["community", "role", "name", "phone", "email", "church_or_office", "notes"]
    branch_lookup = "community__branch"
    sensitive = True


@register
class TeamResource(_Missions):
    model = Team
    slug = "teams"
    label = "Evangelism teams"
    nav_group = "Field"
    list_fields: ClassVar = ["name", "branch", "leader", "focus", "member_count", "is_active"]
    filters: ClassVar = ["branch", "is_active"]
    fields: ClassVar = ["name", "branch", "leader", "focus", "is_active"]
    children: ClassVar = [
        ("members", "team-members", "Members & volunteers"),
        ("campaigns", "campaigns", "Assignments"),
    ]
    branch_lookup = "branch"

    def member_count(self, obj: Team) -> int:
        return obj.members.filter(is_active=True).count()

    member_count.short_description = "Active members"  # type: ignore[attr-defined]


@register
class TeamMemberResource(_Missions):
    model = TeamMember
    slug = "team-members"
    nav = False
    parent_field = "team"
    list_fields: ClassVar = ["name", "role", "is_volunteer", "is_active"]
    fields: ClassVar = ["team", "name", "phone", "role", "is_volunteer", "is_active"]
    branch_lookup = "team__branch"


# ------------------------------------------------------------------------------------------ dashboard
def follow_up_rate(converts: QuerySet) -> int | None:
    total = converts.count()
    if not total:
        return None
    done = converts.filter(follow_up__status__in=["enrolled", "milestone", "completed"]).count()
    return int(done * 100 / total)


@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    campaigns = CampaignResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    reports = ReportResource().get_queryset(access).filter(**filters.branch_filter("campaign__branch_id"))
    converts = ConvertResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    period_reports = reports.filter(report_date__gte=filters.start, report_date__lte=filters.end)
    period_converts = converts.filter(decision_date__gte=filters.start, decision_date__lte=filters.end)
    held = campaigns.filter(
        status=Campaign.Status.COMPLETED, start_date__gte=filters.start, start_date__lte=filters.end
    )
    totals = period_reports.aggregate(reached=Sum("souls_reached"), decisions=Sum("decisions"))
    rate = follow_up_rate(period_converts)
    upcoming = campaigns.filter(start_date__gte=timezone.localdate()).exclude(
        status=Campaign.Status.CANCELLED
    )
    communities = CommunityResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    curl = CampaignResource().url("list")
    kpis = [
        KPI("Campaigns held", held.count(), url=f"{curl}?status=completed", code="campaigns_held"),
        KPI("People reached", totals["reached"] or 0, code="people_reached"),
        KPI("Decisions for Christ", totals["decisions"] or 0, code="decisions"),
        KPI(
            "New converts recorded",
            period_converts.count(),
            url=ConvertResource().url("list"),
            code="converts",
        ),
        KPI(
            "Follow-up completion",
            f"{rate}%" if rate is not None else "—",
            "Converts enrolled in discipleship or beyond",
            code="follow_up_rate",
            status="" if rate is None else ("good" if rate >= 60 else "warn"),
        ),
        KPI(
            "Communities engaged",
            communities.exclude(status=Community.Status.TARGET).count(),
            url=CommunityResource().url("list"),
            code="communities_engaged",
        ),
        KPI("Upcoming campaigns", upcoming.count(), url=curl, code="upcoming"),
    ]
    by_place = (
        period_reports.values("campaign__community__name", "campaign__location")
        .annotate(
            campaigns=Count("campaign", distinct=True),
            reached=Sum("souls_reached"),
            decisions=Sum("decisions"),
        )
        .order_by("-reached")[:15]
    )
    charts = [
        Chart(
            "Decisions for Christ per month",
            "bar",
            monthly_series(reports, "report_date", filters.start, filters.end, sum_field="decisions"),
        ),
        Chart(
            "People reached per month",
            "line",
            monthly_series(reports, "report_date", filters.start, filters.end, sum_field="souls_reached"),
        ),
        Chart(
            "Campaigns by type (period)",
            "hbar",
            grouped_counts(
                campaigns.filter(start_date__gte=filters.start, start_date__lte=filters.end),
                "kind",
                dict(Campaign.Kind.choices),
            ),
        ),
    ]
    sections = [
        {
            "title": "Impact by location (period)",
            "columns": ["Community / location", "Campaigns", "Reached", "Decisions"],
            "rows": [
                [
                    r["campaign__community__name"] or r["campaign__location"] or "Not recorded",
                    r["campaigns"],
                    r["reached"] or 0,
                    r["decisions"] or 0,
                ]
                for r in by_place
            ],
            "empty": "No field reports in this period.",
        }
    ]
    no_report = campaigns.filter(status=Campaign.Status.COMPLETED).annotate(n=Count("reports")).filter(n=0)
    attention = [
        Item(f"Completed but no field report: {c}", "", CampaignResource().url("detail", c), "warn")
        for c in no_report[:5]
    ]
    stuck = converts.filter(
        follow_up__status="new", decision_date__lt=timezone.localdate() - timedelta(days=14)
    )
    attention += [
        Item(f"Not contacted after two weeks: {c}", c.location, ConvertResource().url("detail", c), "bad")
        for c in stuck[:5]
    ]
    activity = [
        Item(
            str(r), f"{r.souls_reached} reached · {r.decisions} decisions", ReportResource().url("detail", r)
        )
        for r in reports.order_by("-created_at")[:6]
    ]
    actions = [
        Action("Submit a field report", ReportResource().url("create"), primary=True),
        Action("Record a new convert", ConvertResource().url("create")),
    ]
    if CampaignResource().can(access, "add"):
        actions.append(Action("Plan a campaign", CampaignResource().url("create")))
    return Dashboard(
        title="Missions & Outreach",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
        sections=sections,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    reports = FieldReport.objects.filter(
        report_date__gte=filters.start,
        report_date__lte=filters.end,
        **filters.branch_filter("campaign__branch_id"),
    )
    totals = reports.aggregate(reached=Sum("souls_reached"), decisions=Sum("decisions"))
    converts = NewConvert.objects.filter(decision_date__gte=filters.start, decision_date__lte=filters.end)
    rate = follow_up_rate(converts)
    return [
        KPI(
            "Campaigns held",
            Campaign.objects.filter(
                status="completed", start_date__gte=filters.start, start_date__lte=filters.end
            ).count(),
        ),
        KPI("People reached", totals["reached"] or 0),
        KPI("Decisions", totals["decisions"] or 0),
        KPI("Follow-up completion", f"{rate}%" if rate is not None else "—"),
    ]
