"""Membership Administration in the staff portal: screens and dashboard."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django.db.models import Model, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from core.people import AgeBand, Gender
from portal.access import HEAD, MEMBER, Access
from portal.charts import Chart, grouped_counts, monthly_series
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
from .forms import MemberForm
from .models import (
    Activity,
    Announcement,
    Attendance,
    BulkMessage,
    Correspondence,
    MeetingMinutes,
    Member,
    MemberDocument,
    ServiceRecord,
    WelfareCase,
)

DEPT = "membership"


class _Membership(Resource):
    department = DEPT
    minor_lookup: str | None = None  # path to Member.is_minor

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        # Minors' records are visible only to the Membership head and the Founder.
        if self.minor_lookup and not access.is_head(DEPT):
            qs = qs.exclude(**{self.minor_lookup: True})
        return qs


@register
class MemberResource(_Membership):
    model = Member
    slug = "members"
    label = "Member register"
    icon = "users"
    description = (
        "Every member and applicant. Applications from the website arrive here as 'Application received'."
    )
    nav_group = "Members"
    list_fields: ClassVar = [
        "member_number",
        "full_name",
        "status",
        "branch",
        "gender",
        "age_band",
        "engagement_score",
    ]
    filters: ClassVar = ["status", "branch", "gender", "age_band", "source", "comms_opt_in"]
    search_fields: ClassVar = ["member_number"]
    form_class = MemberForm
    fields: ClassVar = MemberForm.Meta.fields
    detail_fields: ClassVar = [
        "member_number",
        "status",
        "source",
        "branch",
        "full_name",
        "gender",
        "date_of_birth",
        "age_band",
        "nationality",
        "country",
        "city",
        "phone",
        "email",
        "occupation",
        "born_again",
        "church_attended",
        "years_christian",
        "testimony",
        "talents",
        "declaration",
        "consent",
        "comms_opt_in",
        "guardian_name",
        "guardian_contact",
        "guardian_consent",
        "join_date",
        "orientation_date",
        "transferred_to",
        "engagement_score",
        "decided_at",
        "decision_note",
        "internal_notes",
    ]
    export_fields: ClassVar = [
        "member_number",
        "status",
        "branch",
        "full_name",
        "gender",
        "age_band",
        "country",
        "city",
        "phone",
        "email",
        "join_date",
        "engagement_score",
    ]
    children: ClassVar = [
        ("service_records", "service-records", "Service records"),
        ("welfare_cases", "welfare", "Welfare cases"),
        ("documents", "documents", "Documents"),
        ("attendance", "attendance", "Attendance"),
    ]
    ordering: ClassVar = ["-created_at"]
    date_field = "created_at"
    branch_lookup = "branch"
    minor_lookup = "is_minor"
    sensitive = True

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        member: Member = obj  # type: ignore[assignment]
        if self.effective_level(access) < MEMBER:
            return []
        steps = services.available_transitions(member, is_head=access.is_head(DEPT))
        return [
            {
                "label": services.LABELS[name],
                "url": reverse("portal:membership:member_step", args=[member.pk, name]),
                "method": "get",
                "style": "primary" if name == "approve" else "",
            }
            for name in steps
        ]


class _MemberChild(_Membership):
    nav = False
    parent_field = "member"
    branch_lookup = "member__branch"
    minor_lookup = "member__is_minor"


@register
class ServiceRecordResource(_MemberChild):
    model = ServiceRecord
    slug = "service-records"
    list_fields: ClassVar = ["ministry_area", "role", "start_date", "end_date"]
    fields: ClassVar = ["member", "ministry_area", "role", "start_date", "end_date", "notes"]

    def after_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        services.recompute_engagement(obj.member)  # type: ignore[attr-defined]


@register
class WelfareResource(_MemberChild):
    model = WelfareCase
    slug = "welfare"
    label = "Welfare cases"
    nav = True
    nav_group = "Members"
    list_fields: ClassVar = ["__str__", "member", "status", "opened_on", "assigned_to"]
    filters: ClassVar = ["status", "category"]
    fields: ClassVar = ["member", "category", "summary", "status", "opened_on", "closed_on", "assigned_to"]
    date_field = "opened_on"
    sensitive = True


@register
class MemberDocumentResource(_MemberChild):
    model = MemberDocument
    slug = "documents"
    list_fields: ClassVar = ["title", "created_at"]
    fields: ClassVar = ["member", "title", "file"]
    sensitive = True


@register
class ActivityResource(_Membership):
    model = Activity
    slug = "activities"
    label = "Activities & attendance"
    nav_group = "Participation"
    description = "Services, fellowships, meetings and classes. Open one to take attendance."
    list_fields: ClassVar = ["name", "kind", "date", "branch", "present_count"]
    filters: ClassVar = ["kind", "branch"]
    fields: ClassVar = ["name", "kind", "date", "branch", "event"]
    ordering: ClassVar = ["-date"]
    date_field = "date"
    branch_lookup = "branch"
    branch_actions: ClassVar = {"view", "add", "change"}
    children: ClassVar = [("attendance", "attendance", "Attendance")]

    def present_count(self, obj: Activity) -> int:
        return obj.attendance.filter(present=True).count()

    present_count.short_description = "Present"  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        if not self.can(access, "change"):
            return []
        return [
            {
                "label": "Take attendance",
                "url": reverse("portal:membership:attendance", args=[obj.pk]),
                "method": "get",
                "style": "primary",
            }
        ]


@register
class AttendanceResource(_Membership):
    model = Attendance
    slug = "attendance"
    nav = False
    list_fields: ClassVar = ["activity", "member", "present"]
    branch_lookup = "activity__branch"
    minor_lookup = "member__is_minor"
    perms: ClassVar = {"delete": HEAD}


@register
class AnnouncementResource(_Membership):
    model = Announcement
    slug = "announcements"
    nav_group = "Communications"
    list_fields: ClassVar = ["title", "published_on", "branch"]
    fields: ClassVar = ["title", "body", "branch", "published_on"]
    ordering: ClassVar = ["-published_on"]
    date_field = "published_on"


@register
class MinutesResource(_Membership):
    model = MeetingMinutes
    slug = "minutes"
    label = "Meeting minutes"
    nav_group = "Communications"
    list_fields: ClassVar = ["title", "meeting_date", "branch"]
    fields: ClassVar = ["title", "meeting_date", "branch", "attendees", "minutes", "action_points", "file"]
    date_field = "meeting_date"
    branch_lookup = "branch"


@register
class CorrespondenceResource(_Membership):
    model = Correspondence
    slug = "correspondence"
    label = "Correspondence log"
    nav_group = "Communications"
    list_fields: ClassVar = ["date", "direction", "subject", "counterparty", "reference"]
    filters: ClassVar = ["direction"]
    search_fields: ClassVar = ["subject", "counterparty", "reference"]
    fields: ClassVar = ["direction", "date", "reference", "counterparty", "subject", "summary", "file"]
    date_field = "date"


@register
class BulkMessageResource(_Membership):
    model = BulkMessage
    slug = "messages"
    label = "Messages to members"
    nav_group = "Communications"
    description = (
        "Email or WhatsApp links to members who agreed to receive messages. Under-18s are never included."
    )
    list_fields: ClassVar = ["subject", "channel", "audience", "branch", "sent_at", "recipient_count"]
    fields: ClassVar = ["subject", "body", "channel", "audience", "branch"]
    perms: ClassVar = {"add": MEMBER, "change": MEMBER, "delete": HEAD}

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        return not (action == "change" and obj.sent_at)  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        message: BulkMessage = obj  # type: ignore[assignment]
        if not access.is_head(DEPT) or message.sent_at:
            return []
        if message.channel == BulkMessage.Channel.WHATSAPP:
            return [
                {
                    "label": "Show WhatsApp links",
                    "url": reverse("portal:membership:whatsapp", args=[message.pk]),
                    "method": "get",
                    "style": "primary",
                }
            ]
        return [
            {
                "label": "Send email now",
                "url": reverse("portal:membership:send", args=[message.pk]),
                "style": "primary",
                "confirm": "Send this email to every opted-in member in the chosen audience?",
            }
        ]


# ------------------------------------------------------------------------------------------ dashboard
def scoped_members(access: Access) -> QuerySet:
    return MemberResource().get_queryset(access)


@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    members = scoped_members(access).filter(**filters.branch_filter("branch_id"))
    current = members.filter(status__in=Member.CURRENT)
    active = members.filter(status=Member.Status.ACTIVE)
    pending = members.filter(status__in=Member.PENDING)
    today = timezone.localdate()
    month_start = today.replace(day=1)
    new_in_period = members.filter(join_date__gte=filters.start, join_date__lte=filters.end)
    leavers = members.filter(status__in=[Member.Status.INACTIVE, Member.Status.TRANSFERRED]).count()
    retention = int(active.count() * 100 / (active.count() + leavers)) if (active.count() + leavers) else 0
    welfare = WelfareResource().get_queryset(access).filter(**filters.branch_filter("member__branch_id"))
    open_welfare = welfare.exclude(status=WelfareCase.Status.CLOSED)
    url = MemberResource().url("list")

    kpis = [
        KPI(
            "Members",
            current.count(),
            "Approved, in orientation/integration or active",
            url,
            code="total_members",
        ),
        KPI("Active", active.count(), url=f"{url}?status=active", code="active_members"),
        KPI("New this month", members.filter(join_date__gte=month_start).count(), code="new_this_month"),
        KPI("New in period", new_in_period.count(), code="new_in_period"),
        KPI(
            "Pending approvals",
            pending.count(),
            url=f"{url}?status=submitted",
            code="pending_approvals",
            status="warn" if pending.exists() else "",
        ),
        KPI(
            "Retention",
            f"{retention}%",
            "Active vs. those who became inactive or transferred",
            code="retention",
        ),
        KPI(
            "Welfare cases open", open_welfare.count(), url=WelfareResource().url("list"), code="welfare_open"
        ),
    ]
    charts = [
        Chart(
            "New members per month", "bar", monthly_series(members, "join_date", filters.start, filters.end)
        ),
        Chart("Current members by branch", "hbar", grouped_counts(current, "branch__name")),
        Chart("By gender", "hbar", grouped_counts(current, "gender", dict(Gender.choices))),
        Chart(
            "By age band",
            "bar",
            [(label, current.filter(age_band=code).count()) for code, label in AgeBand.choices],
        ),
    ]
    week_ago = timezone.now() - timedelta(days=7)
    attention = [
        Item(
            f"Application waiting over a week: {m}",
            m.created_at.strftime("%d %b"),
            MemberResource().url("detail", m),
            "warn",
        )
        for m in pending.filter(created_at__lt=week_ago)[:5]
    ]
    attention += [
        Item(f"Under 18 without guardian consent: {m}", "", MemberResource().url("detail", m), "bad")
        for m in pending.filter(is_minor=True, guardian_consent=False)[:5]
    ]
    attention += [
        Item(f"{c} open since {c.opened_on:%d %b}", "", WelfareResource().url("detail", c), "warn")
        for c in open_welfare.filter(opened_on__lt=today - timedelta(days=14))[:5]
    ]
    activity = [
        Item(
            f"{m.get_status_display()}: {m}",
            timezone.localtime(m.updated_at).strftime("%d %b %H:%M"),
            MemberResource().url("detail", m),
        )
        for m in members.order_by("-updated_at")[:6]
    ]
    actions = [
        Action("Review applications", f"{url}?status=submitted", primary=True),
        Action("Add member", MemberResource().url("create")),
        Action("Take attendance", ActivityResource().url("create")),
    ]
    if MinutesResource().can(access, "add"):
        actions += [
            Action("New announcement", AnnouncementResource().url("create")),
            Action("Message members", BulkMessageResource().url("create")),
        ]
    return Dashboard(
        title="Membership Administration",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    members = Member.objects.filter(**filters.branch_filter("branch_id"))
    return [
        KPI("Current members", members.filter(status__in=Member.CURRENT).count()),
        KPI("Active", members.filter(status=Member.Status.ACTIVE).count()),
        KPI(
            "New in period", members.filter(join_date__gte=filters.start, join_date__lte=filters.end).count()
        ),
        KPI("Welfare cases open", WelfareCase.objects.exclude(status=WelfareCase.Status.CLOSED).count()),
    ]


@pending_approvals(DEPT)
def pending() -> list[Item]:
    count = Member.objects.filter(status__in=Member.PENDING).count()
    if not count:
        return []
    return [
        Item(
            f"{count} membership application(s) awaiting a decision",
            "Membership",
            MemberResource().url("list") + "?status=submitted",
            "warn",
        )
    ]
