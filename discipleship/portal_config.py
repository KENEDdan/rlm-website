"""Discipleship in the staff portal."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Avg, Max, Model, Q, QuerySet
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

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
    handoffs,
    pending_approvals,
)
from portal.resources import Resource, register
from resources.models import Resource as PublishedResource

from . import services
from .models import (
    Assessment,
    CheckIn,
    ClassSession,
    Cohort,
    Curriculum,
    Disciple,
    Enrollment,
    FollowUp,
    GrowthArea,
    LeaderCandidate,
    Mentorship,
    PastoralNote,
    Registration,
    SessionAttendance,
)

DEPT = "discipleship"


def discipleship_staff(access: Access) -> QuerySet:
    return (
        get_user_model()
        .objects.filter(is_active=True, deleted_at__isnull=True, memberships__department__code=DEPT)
        .distinct()
    )


class _Discipleship(Resource):
    department = DEPT
    minor_lookup: str | None = None

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        # Under-18s are visible only to the Discipleship head and the Founder.
        if self.minor_lookup and not access.is_head(DEPT):
            qs = qs.exclude(**{self.minor_lookup: True})
        return qs


def _post(url: str, label: str, style: str = "", confirm: str = "") -> dict[str, Any]:
    return {"label": label, "url": url, "style": style, "confirm": confirm}


@register
class RegistrationResource(_Discipleship):
    model = Registration
    slug = "registrations"
    label = "Registrations (website)"
    nav_group = "People"
    list_fields: ClassVar = ["__str__", "status", "gender", "age_band", "country", "created_at"]
    filters: ClassVar = ["status", "gender", "age_band", "branch"]
    fields: ClassVar = ["branch", "guardian_name", "guardian_contact", "guardian_consent"]
    detail_fields: ClassVar = [
        "status",
        "full_name",
        "gender",
        "age",
        "age_band",
        "nationality",
        "country",
        "city",
        "phone",
        "email",
        "born_again",
        "baptized",
        "attends_church",
        "journey",
        "growth_areas",
        "guardian_name",
        "guardian_contact",
        "guardian_consent",
        "branch",
        "created_at",
    ]
    date_field = "created_at"
    branch_lookup = "branch"
    minor_lookup = "is_minor"
    sensitive = True
    perms: ClassVar = {"add": HEAD + 2, "delete": HEAD}

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        reg: Registration = obj  # type: ignore[assignment]
        if self.effective_level(access) < MEMBER or reg.status in (
            Registration.Status.ENROLLED,
            Registration.Status.DECLINED,
        ):
            return []
        out = []
        if reg.status == Registration.Status.SUBMITTED:
            out.append(
                _post(
                    reverse("portal:discipleship:registration_step", args=[reg.pk, "contacted"]),
                    "Mark contacted",
                )
            )
        out.append(
            {
                "label": "Enrol",
                "url": reverse("portal:discipleship:registration_enroll", args=[reg.pk]),
                "method": "get",
                "style": "primary",
            }
        )
        out.append(
            _post(
                reverse("portal:discipleship:registration_step", args=[reg.pk, "declined"]),
                "Not taken forward",
                "danger",
            )
        )
        return out


class DiscipleForm(forms.ModelForm):
    growth_areas = forms.MultipleChoiceField(
        choices=GrowthArea.choices, widget=forms.CheckboxSelectMultiple, required=False
    )

    class Meta:
        model = Disciple
        fields = [
            "full_name",
            "phone",
            "email",
            "gender",
            "age_band",
            "branch",
            "member",
            "growth_areas",
            "stage",
            "mentor",
        ]


@register
class DiscipleResource(_Discipleship):
    model = Disciple
    slug = "disciples"
    nav_group = "People"
    list_fields: ClassVar = ["full_name", "stage", "source", "branch", "mentor", "latest_assessment"]
    filters: ClassVar = ["stage", "source", "branch", "mentor", "age_band"]
    form_class = DiscipleForm
    fields: ClassVar = DiscipleForm.Meta.fields
    detail_fields: ClassVar = [*DiscipleForm.Meta.fields, "source"]
    children: ClassVar = [
        ("enrollments", "enrollments", "Classes"),
        ("mentorships", "mentorships", "Mentorship"),
        ("assessments", "assessments", "Growth assessments"),
        ("pastoral_notes", "pastoral-notes", "Pastoral notes (restricted)"),
    ]
    branch_lookup = "branch"
    minor_lookup = "is_minor"
    sensitive = True
    fk_querysets: ClassVar = {"mentor": discipleship_staff}

    def latest_assessment(self, obj: Disciple) -> str:
        latest = obj.assessments.first()
        return f"{latest.average}/5 ({latest.date:%b %Y})" if latest else "—"

    latest_assessment.short_description = "Latest assessment"  # type: ignore[attr-defined]


@register
class FollowUpResource(_Discipleship):
    model = FollowUp
    slug = "follow-ups"
    label = "New-convert follow-up"
    nav_group = "People"
    description = "Handed over automatically by Missions & Outreach for every decision for Christ."
    list_fields: ClassVar = ["__str__", "convert_name", "status", "due_date", "assigned_to", "campaign"]
    filters: ClassVar = ["status", "assigned_to", "branch"]
    fields: ClassVar = ["assigned_to", "due_date", "notes"]
    detail_fields: ClassVar = [
        "convert_name",
        "convert_phone",
        "convert_location",
        "campaign",
        "decision",
        "consent",
        "status",
        "assigned_to",
        "due_date",
        "last_contact",
        "notes",
        "disciple",
    ]
    date_field = "due_date"
    branch_lookup = "branch"
    minor_lookup = "is_minor"
    sensitive = True
    perms: ClassVar = {"add": HEAD + 2, "delete": HEAD + 2}
    fk_querysets: ClassVar = {"assigned_to": discipleship_staff}

    def convert_name(self, obj: FollowUp) -> str:
        return obj.convert.full_name

    convert_name.short_description = "Name"  # type: ignore[attr-defined]

    def convert_phone(self, obj: FollowUp) -> str:
        return obj.convert.phone or "—"

    convert_phone.short_description = "Phone"  # type: ignore[attr-defined]

    def convert_location(self, obj: FollowUp) -> str:
        return obj.convert.location or "—"

    convert_location.short_description = "Lives in"  # type: ignore[attr-defined]

    def campaign(self, obj: FollowUp) -> str:
        return str(obj.convert.campaign or "—")

    campaign.short_description = "Campaign"  # type: ignore[attr-defined]

    def decision(self, obj: FollowUp) -> str:
        return obj.convert.decision_date.strftime("%d %b %Y")

    decision.short_description = "Decision for Christ"  # type: ignore[attr-defined]

    def consent(self, obj: FollowUp) -> str:
        return "Yes" if obj.convert.consent_to_contact else "NO - do not contact without consent"

    consent.short_description = "Agreed to be contacted"  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        follow: FollowUp = obj  # type: ignore[assignment]
        if self.effective_level(access) < MEMBER:
            return []
        out = []
        for step, (sources, _target) in services.FOLLOW_UP_STEPS.items():
            if follow.status not in sources:
                continue
            url = reverse("portal:discipleship:follow_up_step", args=[follow.pk, step])
            if step == "enroll":
                out.append(
                    {"label": services.STEP_LABELS[step], "url": url, "method": "get", "style": "primary"}
                )
            else:
                out.append(_post(url, services.STEP_LABELS[step], "danger" if step == "lost" else ""))
        return out


@register
class CurriculumResource(_Discipleship):
    model = Curriculum
    slug = "curriculum"
    label = "Curriculum & Bible study materials"
    nav_group = "Classes"
    list_fields: ClassVar = ["title", "level", "resource"]
    search_fields: ClassVar = ["title", "level"]
    fields: ClassVar = ["title", "level", "description", "file", "resource"]
    branch_actions: ClassVar = {"view"}
    fk_querysets: ClassVar = {"resource": lambda access: PublishedResource.objects.filter(is_published=True)}


@register
class CohortResource(_Discipleship):
    model = Cohort
    slug = "cohorts"
    label = "Classes / cohorts"
    nav_group = "Classes"
    list_fields: ClassVar = ["name", "status", "branch", "facilitator", "start_date", "schedule", "enrolled"]
    filters: ClassVar = ["status", "branch", "facilitator"]
    fields: ClassVar = [
        "name",
        "branch",
        "curriculum",
        "facilitator",
        "start_date",
        "end_date",
        "schedule",
        "status",
    ]
    children: ClassVar = [("enrollments", "enrollments", "Enrolled"), ("sessions", "sessions", "Sessions")]
    date_field = "start_date"
    branch_lookup = "branch"
    fk_querysets: ClassVar = {"facilitator": discipleship_staff}

    def enrolled(self, obj: Cohort) -> int:
        return obj.enrollments.filter(status=Enrollment.Status.ENROLLED).count()

    enrolled.short_description = "Enrolled"  # type: ignore[attr-defined]


@register
class EnrollmentResource(_Discipleship):
    model = Enrollment
    slug = "enrollments"
    nav = False
    parent_field = "cohort"
    list_fields: ClassVar = ["disciple", "cohort", "status", "enrolled_on", "completed_on"]
    fields: ClassVar = ["cohort", "disciple", "status", "enrolled_on", "completed_on"]
    branch_lookup = "cohort__branch"
    minor_lookup = "disciple__is_minor"


@register
class SessionResource(_Discipleship):
    model = ClassSession
    slug = "sessions"
    nav = False
    parent_field = "cohort"
    list_fields: ClassVar = ["date", "topic", "present_count"]
    fields: ClassVar = ["cohort", "date", "topic"]
    branch_lookup = "cohort__branch"
    branch_actions: ClassVar = {"view", "add", "change"}

    def present_count(self, obj: ClassSession) -> int:
        return obj.attendance.filter(present=True).count()

    present_count.short_description = "Present"  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        if not self.can(access, "change"):
            return []
        return [
            {
                "label": "Take attendance",
                "url": reverse("portal:discipleship:attendance", args=[obj.pk]),
                "method": "get",
                "style": "primary",
            }
        ]


@register
class SessionAttendanceResource(_Discipleship):
    model = SessionAttendance
    slug = "session-attendance"
    nav = False
    list_fields: ClassVar = ["session", "disciple", "present"]
    branch_lookup = "session__cohort__branch"
    minor_lookup = "disciple__is_minor"


@register
class MentorshipResource(_Discipleship):
    model = Mentorship
    slug = "mentorships"
    label = "Mentorship pairings"
    nav_group = "Growth"
    parent_field = "disciple"
    list_fields: ClassVar = ["mentor", "disciple", "start_date", "end_date", "focus", "last_check_in"]
    filters: ClassVar = ["mentor"]
    fields: ClassVar = ["mentor", "disciple", "start_date", "end_date", "focus"]
    children: ClassVar = [("check_ins", "check-ins", "Accountability check-ins")]
    branch_lookup = "disciple__branch"
    minor_lookup = "disciple__is_minor"
    fk_querysets: ClassVar = {"mentor": discipleship_staff}

    def last_check_in(self, obj: Mentorship) -> str:
        latest = obj.check_ins.first()
        return latest.date.strftime("%d %b %Y") if latest else "None yet"

    last_check_in.short_description = "Last check-in"  # type: ignore[attr-defined]


class _MentorOnly(_Discipleship):
    """Rows visible only to the assigned mentor, the Discipleship head and the Founder."""

    mentor_lookup = "disciple__mentor"
    branch_actions: ClassVar = set()  # Branch Coordinators never see these
    sensitive = True

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        qs = super().scope(access, qs)
        if not access.is_head(DEPT):
            qs = qs.filter(**{self.mentor_lookup: access.user})
        return qs

    def limit_choices(self, access: Access, field_name: str, related: type[Model]) -> QuerySet:
        qs = super().limit_choices(access, field_name, related)
        if related is Disciple and not access.is_head(DEPT):
            qs = qs.filter(mentor=access.user)
        if related is Mentorship and not access.is_head(DEPT):
            qs = qs.filter(mentor=access.user)
        return qs


@register
class CheckInResource(_MentorOnly):
    model = CheckIn
    slug = "check-ins"
    nav = False
    parent_field = "mentorship"
    mentor_lookup = "mentorship__mentor"
    minor_lookup = "mentorship__disciple__is_minor"
    branch_lookup = "mentorship__disciple__branch"
    list_fields: ClassVar = ["date", "next_step"]
    fields: ClassVar = ["mentorship", "date", "summary", "next_step"]


@register
class PastoralNoteResource(_MentorOnly):
    model = PastoralNote
    slug = "pastoral-notes"
    label = "Pastoral notes"
    nav_group = "Growth"
    description = "The most sensitive records: only the disciple's assigned mentor, the head and the Founder see them. Every view is recorded."
    parent_field = "disciple"
    list_fields: ClassVar = ["__str__", "disciple", "author", "created_at"]
    fields: ClassVar = ["disciple", "note"]
    branch_lookup = "disciple__branch"
    minor_lookup = "disciple__is_minor"
    perms: ClassVar = {"export": HEAD + 2, "delete": HEAD}

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        if action == "change":
            return obj.author_id == access.user.pk  # type: ignore[attr-defined]
        return True


@register
class AssessmentResource(_Discipleship):
    model = Assessment
    slug = "assessments"
    label = "Growth assessments"
    nav_group = "Growth"
    parent_field = "disciple"
    list_fields: ClassVar = ["disciple", "date", "average_score", "assessed_by"]
    fields: ClassVar = [
        "disciple",
        "date",
        "knowledge",
        "prayer",
        "gifts",
        "character",
        "evangelism",
        "leadership",
        "maturity",
        "notes",
    ]
    date_field = "date"
    branch_lookup = "disciple__branch"
    minor_lookup = "disciple__is_minor"

    def average_score(self, obj: Assessment) -> str:
        return f"{obj.average}/5"

    average_score.short_description = "Average"  # type: ignore[attr-defined]

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        super().before_save(request, access, obj, created)
        if created:
            obj.assessed_by = request.user  # type: ignore[attr-defined]


@register
class LeaderResource(_Discipleship):
    model = LeaderCandidate
    slug = "leaders"
    label = "Leader development"
    nav_group = "Growth"
    list_fields: ClassVar = ["disciple", "stage", "ministry_area"]
    filters: ClassVar = ["stage"]
    fields: ClassVar = ["disciple", "stage", "ministry_area", "notes"]
    branch_lookup = "disciple__branch"
    minor_lookup = "disciple__is_minor"


# ------------------------------------------------------------------------------------------ dashboard
@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    enrollments = (
        EnrollmentResource().get_queryset(access).filter(**filters.branch_filter("cohort__branch_id"))
    )
    follow = FollowUpResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    cohorts = CohortResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    disciples = DiscipleResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    registrations = RegistrationResource().get_queryset(access).filter(**filters.branch_filter("branch_id"))
    finished = enrollments.filter(status__in=[Enrollment.Status.COMPLETED, Enrollment.Status.DROPPED])
    completion = (
        int(finished.filter(status="completed").count() * 100 / finished.count())
        if finished.exists()
        else None
    )
    awaiting = follow.filter(status__in=FollowUp.OPEN)
    today = timezone.localdate()
    active_mentors = (
        Mentorship.objects.filter(disciple__in=disciples)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .values("mentor")
        .distinct()
        .count()
    )
    furl = FollowUpResource().url("list")
    kpis = [
        KPI("Enrolled now", enrollments.filter(status=Enrollment.Status.ENROLLED).count(), code="enrolled"),
        KPI(
            "Completion rate",
            f"{completion}%" if completion is not None else "—",
            "Completed vs. finished (completed + dropped)",
            code="completion_rate",
        ),
        KPI(
            "Converts awaiting follow-up",
            awaiting.count(),
            url=furl,
            code="awaiting_follow_up",
            status="warn" if awaiting.exists() else "",
        ),
        KPI("Active mentors", active_mentors, url=MentorshipResource().url("list"), code="active_mentors"),
        KPI(
            "Cohorts running",
            cohorts.filter(status=Cohort.Status.RUNNING).count(),
            url=CohortResource().url("list") + "?status=running",
            code="cohorts_running",
        ),
        KPI(
            "New registrations",
            registrations.filter(status=Registration.Status.SUBMITTED).count(),
            url=RegistrationResource().url("list") + "?status=submitted",
            code="new_registrations",
        ),
    ]
    areas = dict(GrowthArea.choices)
    interest = dict.fromkeys(areas, 0)
    for values in list(registrations.values_list("growth_areas", flat=True)) + list(
        disciples.values_list("growth_areas", flat=True)
    ):
        for code in values or []:
            if code in interest:
                interest[code] += 1
    scores = Assessment.objects.filter(
        disciple__in=disciples, date__gte=filters.start, date__lte=filters.end
    ).aggregate(**{a: Avg(a) for a in Assessment.AREAS})
    charts = [
        Chart(
            "New enrolments per month",
            "bar",
            monthly_series(enrollments, "enrolled_on", filters.start, filters.end),
        ),
        Chart("Follow-up pipeline", "hbar", grouped_counts(follow, "status", dict(FollowUp.Status.choices))),
        Chart(
            "Areas people want to grow in",
            "hbar",
            sorted(((areas[k], v) for k, v in interest.items()), key=lambda r: -r[1]),
        ),
        Chart(
            "Average assessment score by area (period, 1-5)",
            "bar",
            [
                (
                    str(areas.get(a, a)).split(" ")[0].title() if a != "knowledge" else "Knowledge",
                    round(scores[a] or 0, 1),
                )
                for a in Assessment.AREAS
            ],
        ),
    ]
    overdue = list(awaiting.filter(status=FollowUp.Status.NEW, due_date__lt=today)[:6])
    attention = [
        Item(
            f"Overdue first contact: {f.convert.full_name}",
            f"Due {f.due_date:%d %b}",
            FollowUpResource().url("detail", f),
            "bad",
        )
        for f in overdue
    ]
    old = registrations.filter(
        status=Registration.Status.SUBMITTED, created_at__lt=timezone.now() - timedelta(days=7)
    )
    attention += [
        Item(f"Registration waiting over a week: {r}", "", RegistrationResource().url("detail", r), "warn")
        for r in old[:5]
    ]
    quiet = (
        MentorshipResource()
        .get_queryset(access)
        .filter(Q(end_date__isnull=True) | Q(end_date__gte=today))
        .annotate(last=Max("check_ins__date"))
        .filter(Q(last__isnull=True) | Q(last__lt=today - timedelta(days=30)))
    )
    attention += [
        Item(f"No check-in for 30 days: {m}", "", MentorshipResource().url("detail", m), "warn")
        for m in quiet[:5]
    ]
    activity = [
        Item(
            f"{f.get_status_display()}: {f.convert.full_name}",
            f.updated_at.strftime("%d %b"),
            FollowUpResource().url("detail", f),
        )
        for f in follow.order_by("-updated_at")[:6]
    ]
    actions = [
        Action("Follow up new converts", furl + "?status=new", primary=True),
        Action("Review registrations", RegistrationResource().url("list") + "?status=submitted"),
        Action("Start a class", CohortResource().url("create")),
        Action("Record an assessment", AssessmentResource().url("create")),
    ]
    return Dashboard(
        title="Discipleship",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    return [
        KPI("Enrolled now", Enrollment.objects.filter(status=Enrollment.Status.ENROLLED).count()),
        KPI("Converts awaiting follow-up", FollowUp.objects.filter(status__in=FollowUp.OPEN).count()),
        KPI("Cohorts running", Cohort.objects.filter(status=Cohort.Status.RUNNING).count()),
        KPI("New registrations", Registration.objects.filter(status=Registration.Status.SUBMITTED).count()),
    ]


@pending_approvals(DEPT)
def pending() -> list[Item]:
    count = Registration.objects.filter(status=Registration.Status.SUBMITTED).count()
    if not count:
        return []
    return [
        Item(
            f"{count} discipleship registration(s) to respond to",
            "Discipleship",
            RegistrationResource().url("list") + "?status=submitted",
            "warn",
        )
    ]


@handoffs
def missions_to_discipleship() -> list[Item]:
    by_status = {s: FollowUp.objects.filter(status=s).count() for s in FollowUp.Status.values}
    if not any(by_status.values()):
        return []
    labels = dict(FollowUp.Status.choices)
    overdue = FollowUp.objects.filter(status="new", due_date__lt=timezone.localdate()).count()
    parts = ", ".join(
        f"{by_status[s]} {str(labels[s]).lower()}" for s in FollowUp.Status.values if by_status[s]
    )
    return [
        Item(
            f"Missions → Discipleship (new converts): {parts}",
            f"{overdue} overdue first contact" if overdue else "",
            FollowUpResource().url("list"),
            "bad" if overdue else "",
        )
    ]
