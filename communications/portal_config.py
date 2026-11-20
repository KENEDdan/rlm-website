"""Media & Communications in the staff portal (incl. the public media archive and hero slides)."""

from __future__ import annotations

from datetime import timedelta
from typing import Any, ClassVar

from django.db.models import Count, Model, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from core.models import HeroSlide
from events.models import Event
from media_library.models import Album, Photo, Testimony, Video
from portal.access import HEAD, Access
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

from .models import Channel, ContentItem, DesignRequest, EventCoverage, SocialReach

DEPT = "media"


class _Media(Resource):
    department = DEPT


@register
class ContentResource(_Media):
    model = ContentItem
    slug = "content"
    label = "Content calendar"
    nav_group = "Publishing"
    description = "Idea → in production → review → published, across the website and social channels."
    list_fields: ClassVar = ["planned_date", "title", "channel", "stage", "assigned_to", "published_on"]
    filters: ClassVar = ["channel", "stage", "assigned_to"]
    search_fields: ClassVar = ["title"]
    fields: ClassVar = [
        "title",
        "channel",
        "stage",
        "planned_date",
        "published_on",
        "assigned_to",
        "event",
        "link",
        "notes",
    ]
    date_field = "planned_date"
    ordering: ClassVar = ["planned_date"]


@register
class DesignResource(_Media):
    model = DesignRequest
    slug = "design-requests"
    label = "Design requests"
    nav_group = "Publishing"
    description = "Posters, banners and flyers. Any department can ask here and follow its own requests."
    list_fields: ClassVar = ["title", "kind", "requesting_department", "needed_by", "status", "assigned_to"]
    filters: ClassVar = ["status", "kind", "requesting_department"]
    fields: ClassVar = [
        "title",
        "kind",
        "requesting_department",
        "needed_by",
        "brief",
        "event",
        "status",
        "assigned_to",
        "artwork",
    ]
    date_field = "needed_by"
    ordering: ClassVar = ["needed_by"]
    requester_field = "requesting_department"
    requester_actions: ClassVar = {"view", "add"}

    def get_form_class(self, access: Access, obj: Model | None = None):  # type: ignore[no-untyped-def]
        if self.requester_mode(access):
            from django.forms import modelform_factory

            from portal.resources import DateInput

            return modelform_factory(
                DesignRequest,
                fields=["title", "kind", "requesting_department", "needed_by", "brief", "event"],
                widgets={"needed_by": DateInput()},
            )
        return super().get_form_class(access, obj)


@register
class CoverageResource(_Media):
    model = EventCoverage
    slug = "coverage"
    branch_lookup = "event__branch"
    label = "Event coverage"
    nav_group = "Publishing"
    list_fields: ClassVar = ["event", "photographer", "videographer", "live_stream", "status"]
    filters: ClassVar = ["status"]
    fields: ClassVar = ["event", "photographer", "videographer", "live_stream", "status", "notes"]
    initial_from_query: ClassVar = ["event"]


@register
class ReachResource(_Media):
    model = SocialReach
    slug = "social-reach"
    label = "Social reach (manual)"
    nav_group = "Publishing"
    description = (
        "Typed in monthly from each platform's own insights. No tracking scripts are used on the website."
    )
    list_fields: ClassVar = ["month", "channel", "followers", "reach", "engagements"]
    filters: ClassVar = ["channel"]
    fields: ClassVar = ["month", "channel", "followers", "reach", "engagements"]
    date_field = "month"


# ---------------------------------------------------------------- the public media archive, managed here
@register
class AlbumResource(_Media):
    model = Album
    slug = "albums"
    branch_lookup = "branch"
    label = "Photo albums"
    nav_group = "Media archive (public site)"
    list_fields: ClassVar = ["title", "branch", "event", "is_published", "photo_count"]
    filters: ClassVar = ["is_published", "branch"]
    search_fields: ClassVar = ["title"]
    fields: ClassVar = [
        "title",
        "slug",
        "description",
        "branch",
        "event",
        "cover",
        "cover_alt",
        "is_published",
    ]
    children: ClassVar = [("photos", "photos", "Photos")]

    def photo_count(self, obj: Album) -> int:
        return obj.photos.count()

    photo_count.short_description = "Photos"  # type: ignore[attr-defined]


@register
class PhotoResource(_Media):
    model = Photo
    slug = "photos"
    branch_lookup = "album__branch"
    nav = False
    parent_field = "album"
    list_fields: ClassVar = ["alt_text", "caption", "is_published"]
    fields: ClassVar = ["album", "image", "alt_text", "caption", "is_published"]


@register
class VideoResource(_Media):
    model = Video
    slug = "videos"
    branch_lookup = "album__branch"
    nav_group = "Media archive (public site)"
    list_fields: ClassVar = ["title", "album", "is_published"]
    filters: ClassVar = ["is_published"]
    fields: ClassVar = ["title", "slug", "youtube_url", "description", "album", "is_published"]


@register
class TestimonyResource(_Media):
    model = Testimony
    slug = "testimonies"
    branch_lookup = "branch"
    label = "Testimonies"
    nav_group = "Media archive (public site)"
    description = "Only consented, approved testimonies of adults appear on the website."
    list_fields: ClassVar = ["title", "consent_confirmed", "subject_is_adult", "is_approved", "is_published"]
    filters: ClassVar = ["is_approved", "is_published", "consent_confirmed", "subject_is_adult"]
    fields: ClassVar = [
        "title",
        "slug",
        "person_display_name",
        "name_display",
        "full_name_consent",
        "consent_confirmed",
        "subject_is_adult",
        "body",
        "photo",
        "photo_alt",
        "branch",
        "is_published",
    ]
    detail_fields: ClassVar = [*fields, "is_approved"]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        t: Testimony = obj  # type: ignore[assignment]
        if not access.is_head(DEPT):
            return []
        url = reverse("portal:communications:testimony_approval", args=[t.pk])
        if t.is_approved:
            return [{"label": "Withdraw approval", "url": url, "fields": {"approve": "0"}, "style": "danger"}]
        return [
            {"label": "Approve for the website", "url": url, "fields": {"approve": "1"}, "style": "primary"}
        ]


@register
class HeroSlideResource(_Media):
    model = HeroSlide
    slug = "hero-slides"
    label = "Home page hero slides"
    nav_group = "Media archive (public site)"
    list_fields: ClassVar = ["order", "title", "is_active", "start_at", "end_at"]
    filters: ClassVar = ["is_active"]
    fields: ClassVar = [
        "title",
        "subtitle",
        "image",
        "image_alt",
        "button_text",
        "button_link",
        "show_scripture",
        "order",
        "is_active",
        "start_at",
        "end_at",
    ]
    ordering: ClassVar = ["order"]
    perms: ClassVar = {"delete": HEAD}


# ------------------------------------------------------------------------------------------ dashboard
@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    content = ContentResource().get_queryset(access)
    in_period = content.filter(planned_date__gte=filters.start, planned_date__lte=filters.end)
    planned = in_period.count()
    published = in_period.filter(stage=ContentItem.Stage.PUBLISHED).count()
    designs = DesignResource().get_queryset(access)
    open_designs = designs.filter(status__in=DesignRequest.OPEN)
    today = timezone.localdate()
    soon = timezone.now() + timedelta(days=30)
    upcoming = Event.objects.filter(start__gte=timezone.now(), start__lte=soon)
    if filters.branch_id:
        upcoming = upcoming.filter(branch_id=filters.branch_id)
    uncovered = upcoming.exclude(coverage__isnull=False)
    pending_t = TestimonyResource().get_queryset(access).filter(is_approved=False)
    archive = PhotoResource().get_queryset(access).count() + VideoResource().get_queryset(access).count()
    reach = ReachResource().get_queryset(access).filter(month__gte=filters.start, month__lte=filters.end)
    curl = ContentResource().url("list")
    kpis = [
        KPI(
            "Published vs planned",
            f"{published} / {planned}",
            "Content items in the period",
            curl,
            code="published_vs_planned",
            status="" if not planned else ("good" if published >= planned * 0.8 else "warn"),
        ),
        KPI(
            "Events needing coverage (30 days)",
            uncovered.count(),
            url=CoverageResource().url("list"),
            code="events_uncovered",
            status="warn" if uncovered.exists() else "",
        ),
        KPI(
            "Design requests open", open_designs.count(), url=DesignResource().url("list"), code="design_open"
        ),
        KPI(
            "Testimonies awaiting approval",
            pending_t.count(),
            url=TestimonyResource().url("list") + "?is_approved=0",
            code="testimonies_pending",
        ),
        KPI("Archive size", archive, "Photos + videos on the website", code="archive_size"),
        KPI(
            "Social reach (period)",
            f"{reach.aggregate(t=Sum('reach'))['t'] or 0:,}",
            "Entered by hand from platform insights",
            ReachResource().url("list"),
            code="social_reach",
        ),
    ]
    channels = dict(Channel.choices)
    charts = [
        Chart(
            "Content published per month",
            "bar",
            monthly_series(content.filter(stage="published"), "published_on", filters.start, filters.end),
        ),
        Chart(
            "Pipeline (all open items)",
            "hbar",
            grouped_counts(content.exclude(stage="published"), "stage", dict(ContentItem.Stage.choices)),
        ),
        Chart(
            "Published by channel (period)",
            "hbar",
            grouped_counts(in_period.filter(stage="published"), "channel", channels),
        ),
        Chart(
            "Social reach per month (manual)",
            "line",
            monthly_series(
                ReachResource().get_queryset(access), "month", filters.start, filters.end, sum_field="reach"
            ),
        ),
    ]
    attention = [
        Item(
            f"No coverage plan: {e.title}",
            e.start.strftime("%d %b"),
            CoverageResource().url("create", event=e.pk),
            "warn",
        )
        for e in uncovered[:5]
    ]
    attention += [
        Item(
            f"Late: {d}",
            f"Needed {d.needed_by:%d %b} · {d.requesting_department}",
            DesignResource().url("detail", d),
            "bad",
        )
        for d in open_designs.filter(needed_by__lt=today)[:5]
    ]
    attention += [
        Item(f"Testimony to review: {t}", "", TestimonyResource().url("detail", t), "") for t in pending_t[:3]
    ]
    attention += [
        Item(f"Planned for today but not published: {c}", "", ContentResource().url("detail", c), "warn")
        for c in content.filter(planned_date__lt=today).exclude(stage="published")[:5]
    ]
    activity = [
        Item(str(c), c.get_stage_display(), ContentResource().url("detail", c))
        for c in content.order_by("-updated_at")[:6]
    ]
    actions = [
        Action("Plan content", ContentResource().url("create"), primary=True),
        Action("Design requests", DesignResource().url("list")),
        Action("Hero slides", HeroSlideResource().url("list")),
        Action("Enter social figures", ReachResource().url("create")),
    ]
    return Dashboard(
        title="Media & Communications",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    items = ContentItem.objects.filter(planned_date__gte=filters.start, planned_date__lte=filters.end)
    return [
        KPI("Published / planned", f"{items.filter(stage='published').count()} / {items.count()}"),
        KPI("Design requests open", DesignRequest.objects.filter(status__in=DesignRequest.OPEN).count()),
        KPI("Testimonies to review", Testimony.objects.filter(is_approved=False).count()),
        KPI("Archive items", Photo.objects.count() + Video.objects.count()),
    ]


@pending_approvals(DEPT)
def pending() -> list[Item]:
    count = Testimony.objects.filter(is_approved=False, consent_confirmed=True).count()
    if not count:
        return []
    return [
        Item(
            f"{count} testimon{'y' if count == 1 else 'ies'} awaiting approval",
            "Media",
            TestimonyResource().url("list") + "?is_approved=0",
            "",
        )
    ]


@handoffs
def design_handoffs() -> list[Item]:
    rows = (
        DesignRequest.objects.filter(status__in=DesignRequest.OPEN)
        .values_list("requesting_department__name")
        .annotate(n=Count("pk"))
        .order_by("-n")
    )
    if not rows:
        return []
    parts = ", ".join(f"{name}: {n}" for name, n in rows)
    return [Item(f"Design requests to Media: {parts}", "", DesignResource().url("list"), "")]
