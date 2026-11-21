"""Part 1: four activity categories and thirteen activities, routed to staff departments."""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from accounts.roles import DISCIPLESHIP, FINANCE, MISSIONS, TECHNICAL
from branches.models import Branch
from events.models import Event
from programs.models import Activity, ActivityCategory

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL

EXPECTED = {
    "Charitable and Humanitarian Services": (
        "development",
        [
            "Children, Women, and Family Programme",
            "Peace Building Initiative",
            "Livelihood Skills Development",
        ],
    ),
    "Evangelism and Missions": (
        "missions",
        ["School Outreach Programme", "Prison, Hospital and Community Visitations", "Open-Air Crusades"],
    ),
    "Discipleship": (
        "discipleship",
        ["Mentorship Programme", "Leadership and Ministerial Trainings", "Internship Discipleship Course"],
    ),
    "Revival Programme": (
        "missions",
        [
            "Annual Youth Revival Conference",
            "Monthly Youth Revival Fellowship",
            "Prayer and Intercession",
            "Seminars",
        ],
    ),
}


def test_exactly_four_categories_and_thirteen_activities_with_exact_names() -> None:
    categories = list(ActivityCategory.objects.order_by("order"))
    assert [c.title for c in categories] == list(EXPECTED)
    for category in categories:
        names = list(category.activities.order_by("order").values_list("title", flat=True))
        assert names == EXPECTED[category.title][1]
    assert Activity.objects.count() == 13
    assert not ActivityCategory.objects.filter(is_published=False).exists()


def test_default_department_routing() -> None:
    for category in ActivityCategory.objects.select_related("department"):
        code = EXPECTED[category.title][0]
        assert category.department.code == code
        assert set(category.activities.values_list("department__code", flat=True)) == {code}


def test_new_activity_inherits_its_categorys_department() -> None:
    category = ActivityCategory.objects.get(slug="discipleship")
    activity = Activity.objects.create(category=category, title="New course", slug="new-course", summary="x")
    assert activity.department.code == "discipleship"


def test_activities_page_groups_by_category_and_detail_shows_events_and_cta(client: Client) -> None:
    html = client.get("/activities/").content.decode()
    for title in EXPECTED:
        assert title in html
    assert "Open-Air Crusades" in html
    crusades = Activity.objects.get(slug="open-air-crusades")
    Event.objects.create(
        title="Crusade in Yei",
        slug="crusade-yei",
        summary="x",
        activity=crusades,
        start=timezone.now() + timedelta(days=5),
        end=timezone.now() + timedelta(days=6),
        is_published=True,
    )
    detail = client.get("/activities/open-air-crusades/").content.decode()
    assert "Crusade in Yei" in detail and "Get involved" in detail and "/get-involved/" in detail
    assert "Evangelism and Missions" in detail
    category = client.get("/activities/category/revival-programme/").content.decode()
    assert "Seminars" in category and "Open-Air Crusades" not in category


def test_home_shows_the_four_categories(client: Client) -> None:
    html = client.get("/").content.decode()
    for title in EXPECTED:
        assert title in html
    assert "Monthly Youth Revival Fellowship" in html


def test_unpublished_activity_and_category_are_hidden(client: Client) -> None:
    ActivityCategory.objects.filter(slug="discipleship").update(is_published=False)
    assert client.get("/activities/mentorship-programme/").status_code == 404
    assert "Mentorship Programme" not in client.get("/activities/").content.decode()


def test_old_programme_urls_redirect_permanently(client: Client) -> None:
    resp = client.get("/programs/")
    assert resp.status_code == 301 and resp["Location"] == "/activities/"
    resp = client.get("/programs/youth-revival-conferences/")
    assert resp.status_code == 301 and resp["Location"] == "/activities/annual-youth-revival-conference/"
    assert client.get("/programs/unknown/")["Location"] == "/activities/"


def test_activity_branch_availability(client: Client) -> None:
    juba = Branch.objects.get(slug="juba")
    seminars = Activity.objects.get(slug="seminars")
    seminars.branches.add(juba)
    assert set(Activity.objects.for_branch(juba)) == set(Activity.objects.all())
    yei = Branch.objects.get(slug="yei")
    assert seminars not in Activity.objects.for_branch(yei)
    assert "Juba" in client.get("/activities/seminars/").content.decode()


def test_activities_feed_the_routed_department_dashboard(make_staff: Any, verified_client: Any) -> None:
    missions = verified_client(make_staff(MISSIONS))
    html = missions.get(P + "missions/").content.decode()
    assert "Our activities" in html and "Open-Air Crusades" in html and "Seminars" in html
    assert "Mentorship Programme" not in html
    disc = verified_client(make_staff(DISCIPLESHIP)).get(P + "discipleship/").content.decode()
    assert "Mentorship Programme" in disc and "Open-Air Crusades" not in disc
    fin = verified_client(make_staff(FINANCE)).get(P + "finance/").content.decode()
    assert "Our activities" not in fin


def test_super_admin_changes_routing_and_dashboard_follows(make_staff: Any, verified_client: Any) -> None:
    from portal.models import Department

    Activity.objects.filter(slug="seminars").update(department=Department.objects.get(code="discipleship"))
    disc = verified_client(make_staff(DISCIPLESHIP)).get(P + "discipleship/").content.decode()
    assert "Seminars" in disc


def test_only_super_admin_can_edit_activity_department_in_admin(
    make_staff: Any, verified_client: Any, admin_prefix: str
) -> None:
    activity = Activity.objects.get(slug="seminars")
    url = f"{admin_prefix}programs/activity/{activity.pk}/change/"
    tech = verified_client(make_staff(TECHNICAL)).get(url).content.decode()
    assert 'name="department"' not in tech and 'name="title"' in tech
    admin = verified_client(make_staff(superuser=True)).get(url).content.decode()
    assert 'name="department"' in admin


def test_branch_scoped_event_counts_on_the_dashboard(make_staff: Any, verified_client: Any) -> None:
    from portal.access import Access
    from portal.activity_panel import activity_rows

    juba, yei = Branch.objects.get(slug="juba"), Branch.objects.get(slug="yei")
    crusades = Activity.objects.get(slug="open-air-crusades")
    soon = timezone.now() + timedelta(days=3)
    for branch, slug in ((juba, "a"), (yei, "b")):
        Event.objects.create(
            title=slug, slug=slug, summary="x", activity=crusades, branch=branch, start=soon,
            end=soon + timedelta(hours=2), is_published=True,
        )  # fmt: skip
    leader = make_staff(MISSIONS)
    coordinator = make_staff(MISSIONS, scoped={"missions": juba})
    count = {r["activity"].slug: r["events"] for r in activity_rows(Access(leader), "missions")}
    assert count["open-air-crusades"] == 2
    count = {r["activity"].slug: r["events"] for r in activity_rows(Access(coordinator), "missions")}
    assert count["open-air-crusades"] == 1


def test_outreach_and_cohort_forms_reference_activities(make_staff: Any, verified_client: Any) -> None:
    client = verified_client(make_staff(MISSIONS))
    html = client.get(P + "missions/campaigns/new/").content.decode()
    assert 'name="activity"' in html and "Open-Air Crusades" in html
    disc = verified_client(make_staff(DISCIPLESHIP)).get(P + "discipleship/cohorts/new/").content.decode()
    assert 'name="activity"' in disc


def test_indicators_can_reference_an_activity() -> None:
    from portal.models import Department, Indicator

    fellowship = Activity.objects.get(slug="monthly-youth-revival-fellowship")
    indicator = Indicator.objects.create(
        department=Department.objects.get(code="missions"), category="youth", name="Fellowship attendance",
        year=timezone.localdate().year, annual_target=1200, activity=fellowship,
    )  # fmt: skip
    assert list(fellowship.indicators.all()) == [indicator]
