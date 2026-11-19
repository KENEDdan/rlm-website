"""Portal shell: landing per role, department scoping, executive overview, M&E indicators and reports."""

from __future__ import annotations

from datetime import date
from io import StringIO

import pytest
from django.conf import settings
from django.test import Client

from accounts.roles import BRANCH_COORDINATOR, EXECUTIVE, FINANCE, FOUNDER, MEDIA, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from portal.access import DEPARTMENT_ORDER, Access
from portal.charts import Chart, monthly_series
from portal.models import Department, DepartmentReport, Indicator, IndicatorValue
from portal.resources import REGISTRY

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def test_anonymous_and_unverified_users_are_sent_to_login(client: Client, make_staff) -> None:  # type: ignore[no-untyped-def]
    assert "login" in client.get(P).url
    assert "login" in client.get(P + "finance/").url
    user = make_staff(FINANCE)
    client.force_login(user)  # password session without 2FA (e.g. created by some other code path)
    resp = client.get(P + "finance/")
    assert resp.status_code == 302 and "login" in resp.url


def test_each_user_lands_on_their_own_dashboard(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    assert verified_client(make_staff(MEDIA)).get(P)["Location"] == P + "media/"
    assert verified_client(make_staff(FOUNDER, superuser=True)).get(P)["Location"] == P + "executive/"
    assert verified_client(make_staff(EXECUTIVE)).get(P)["Location"] == P + "executive/"
    assert verified_client(make_staff()).get(P)["Location"] == P + "no-access/"


@pytest.mark.parametrize("code", DEPARTMENT_ORDER)
def test_department_dashboards_are_isolated(code: str, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    outsider = verified_client(make_staff(email=f"{code}@example.test"))
    assert outsider.get(P + f"{code}/").status_code == 403
    client = verified_client(make_staff(email=f"own-{code}@example.test", members={code}))
    assert client.get(P + f"{code}/").status_code == 200
    for other in DEPARTMENT_ORDER:
        if other != code:
            assert client.get(P + f"{other}/").status_code == 403, other


def test_user_with_two_departments_sees_both_and_sidebar_shows_only_them(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(FINANCE, MEDIA))
    page = client.get(P + "finance/")
    assert page.status_code == 200
    html = page.content.decode()
    assert "Media &amp; Communications" in html and "Finance &amp; Resource Mobilization" in html
    assert "Discipleship" not in html and "Staff accounts" not in html
    assert client.get(P + "media/").status_code == 200


def test_executive_overview_access(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    assert verified_client(make_staff(FINANCE)).get(P + "executive/").status_code == 403
    page = verified_client(make_staff(EXECUTIVE)).get(P + "executive/")
    assert page.status_code == 200
    # executive leadership sees totals but no drill-down into departments they do not belong to
    assert f'href="{P}finance/"' not in page.content.decode()
    founder_page = verified_client(make_staff(FOUNDER, superuser=True)).get(P + "executive/")
    assert f'href="{P}finance/"' in founder_page.content.decode()


def test_branch_coordinator_gets_branch_level_in_three_departments(make_staff) -> None:  # type: ignore[no-untyped-def]
    juba = Branch.objects.get(slug="juba")
    access = Access(make_staff(BRANCH_COORDINATOR, branch=juba))
    assert access.departments() == ["membership", "missions", "discipleship"]
    assert not access.can_enter("finance")
    assert list(access.allowed_branches()) == [juba]
    no_branch = Access(make_staff(BRANCH_COORDINATOR))
    assert not no_branch.allowed_branches().exists()


def test_dashboard_branch_filter_cannot_be_widened_by_a_coordinator(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    juba, yei = Branch.objects.get(slug="juba"), Branch.objects.get(slug="yei")
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))
    page = client.get(P + f"membership/?branch={yei.pk}")
    assert page.status_code == 200
    assert page.context["filters"].branch_id == juba.pk


# ------------------------------------------------------------------ M&E
def _indicator(code: str = "finance", **kw) -> Indicator:  # type: ignore[no-untyped-def]
    return Indicator.objects.create(
        department=Department.objects.get(code=code), name=kw.pop("name", "Funds raised"), target=100, **kw
    )


def test_indicators_are_scoped_per_department(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    mine, theirs = _indicator("finance"), _indicator("membership", name="New members")
    client = verified_client(make_staff(FINANCE))
    listing = client.get(P + "finance/indicators/").content.decode()
    assert "Funds raised" in listing and "New members" not in listing
    assert client.get(P + f"finance/indicators/{mine.pk}/").status_code == 200
    assert client.get(P + f"finance/indicators/{theirs.pk}/").status_code == 404  # IDOR -> 404
    assert client.get(P + f"membership/indicators/{theirs.pk}/").status_code == 403


def test_only_heads_define_targets_members_record_values(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    member = verified_client(make_staff(FINANCE))
    data = {
        "name": "Grants won",
        "unit": "number",
        "target": "4",
        "period": "quarterly",
        "higher_is_better": "on",
        "is_active": "on",
    }
    assert member.post(P + "finance/indicators/new/", data).status_code == 403
    head = verified_client(make_staff(FINANCE, heads={"finance"}))
    resp = head.post(P + "finance/indicators/new/", data)
    assert resp.status_code == 302
    indicator = Indicator.objects.get(name="Grants won")
    assert indicator.department.code == "finance"
    resp = member.post(
        P + "finance/indicator-values/new/",
        {"indicator": indicator.pk, "period_start": "2026-07-01", "value": "3", "note": ""},
    )
    assert resp.status_code == 302
    value = IndicatorValue.objects.get(indicator=indicator)
    assert value.progress == 75
    # a value pointing at another department's indicator is refused (FK choices are scoped)
    other = _indicator("media", name="Posts")
    resp = member.post(
        P + "finance/indicator-values/new/",
        {"indicator": other.pk, "period_start": "2026-07-01", "value": "3", "note": ""},
    )
    assert resp.status_code == 200 and not IndicatorValue.objects.filter(indicator=other).exists()


def test_indicator_value_must_start_the_period() -> None:
    from django.core.exceptions import ValidationError

    value = IndicatorValue(indicator=_indicator(), period_start=date(2026, 7, 15), value=1)
    with pytest.raises(ValidationError):
        value.full_clean()


def test_report_generate_submit_review_cycle(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    _indicator("membership", name="Active members", auto_source="active_members", higher_is_better=True)
    head_user = make_staff(MEMBERSHIP, heads={"membership"})
    head = verified_client(head_user)
    member = verified_client(make_staff(MEMBERSHIP))
    assert member.post(P + "membership/reports/generate/", {"month": "2026-10"}).status_code == 403
    resp = head.post(P + "membership/reports/generate/", {"month": "2026-10", "period": "monthly"})
    assert resp.status_code == 302
    report = DepartmentReport.objects.get()
    assert report.period_start == date(2026, 10, 1) and report.period_end == date(2026, 10, 31)
    assert isinstance(report.figures, list) and report.status == "draft"
    edit = head.post(
        P + f"membership/reports/{report.pk}/edit/",
        {"highlights": "Good month", "challenges": "", "plans_next_period": "", "support_needed": ""},
    )
    assert edit.status_code == 302
    assert head.post(P + f"membership/reports/{report.pk}/submit/").status_code == 302
    report.refresh_from_db()
    assert report.status == "submitted" and report.highlights == "Good month"
    # submitted reports are locked
    assert head.get(P + f"membership/reports/{report.pk}/edit/").status_code == 403
    # only the Super Admin reviews
    assert head.post(P + f"membership/reports/{report.pk}/review/", {"decision": "accept"}).status_code == 403
    founder = verified_client(make_staff(FOUNDER, superuser=True))
    overview = founder.get(P + "executive/").content.decode()
    assert "Awaiting your review" in overview or "Submitted" in overview
    founder.post(
        P + f"membership/reports/{report.pk}/review/", {"decision": "return", "comment": "Add numbers"}
    )
    report.refresh_from_db()
    assert report.status == "returned" and report.review_comment == "Add numbers"
    assert head.get(P + f"membership/reports/{report.pk}/edit/").status_code == 200
    assert AuditLog.objects.filter(action=AuditLog.Action.SUBMIT, object_id=str(report.pk)).exists()


def test_dashboard_export_is_head_only_and_audited(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    assert verified_client(make_staff(MEDIA)).get(P + "media/export/csv/").status_code == 403
    head = verified_client(make_staff(MEDIA, heads={"media"}))
    resp = head.get(P + "media/export/csv/")
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
    assert head.get(P + "media/export/print/").status_code == 200
    assert AuditLog.objects.filter(action=AuditLog.Action.EXPORT, extra__dashboard="media").count() == 2


def test_every_registered_resource_denies_outsiders(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    """No department screen is reachable by staff with no role in that department."""
    client = verified_client(make_staff(EXECUTIVE))
    for (department, slug), resource in REGISTRY.items():
        if resource.requester_field:
            continue
        assert client.get(P + f"{department}/{slug}/").status_code == 403, (department, slug)
        assert client.get(P + f"{department}/{slug}/export.csv").status_code == 403, (department, slug)


def test_charts_render_geometry() -> None:
    chart = Chart("Members", "bar", [("Jan", 3), ("Feb", 0), ("Mar", 6)])
    bars = chart.geometry["bars"]
    assert len(bars) == 3 and bars[2]["h"] > bars[0]["h"] > bars[1]["h"] == 0
    assert Chart("x", "line", [("a", 1)]).geometry["path"].startswith("M")
    assert Chart("x", "hbar", [("a", 2), ("b", 1)]).geometry["rows"][1]["pct"] == 50.0
    assert Chart("x", "bar", []).is_empty


def test_monthly_series_fills_gaps() -> None:
    _indicator()
    series = monthly_series(Indicator.objects.all(), "created_at", date(2026, 1, 1), date(2026, 12, 31))
    assert len(series) == 12


def test_workflow_urls_never_shadow_generic_resource_routes() -> None:
    from django.urls import resolve

    for department, slug in REGISTRY:
        base = f"{P}{department}/{slug}/"
        assert resolve(base).url_name == "resource_list", base
        assert resolve(base + "new/").url_name == "resource_create", base
        assert resolve(base + "export.csv").url_name == "resource_export", base
        assert resolve(base + "1/").url_name == "resource_detail", base
        assert resolve(base + "1/edit/").url_name == "resource_edit", base
        assert resolve(base + "1/delete/").url_name == "resource_delete", base


def test_suggested_indicators_point_at_real_dashboard_figures(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from django.core.management import call_command

    from portal.management.commands.seed_indicators import SUGGESTED

    call_command("seed_indicators", stdout=StringIO())
    call_command("seed_indicators", stdout=StringIO())  # idempotent
    assert Indicator.objects.count() == sum(len(rows) for rows in SUGGESTED.values())
    founder = verified_client(make_staff(superuser=True))
    for code, rows in SUGGESTED.items():
        figures = {k.code for k in founder.get(P + f"{code}/").context["board"].kpis}
        for _name, _unit, _target, _higher, source, _desc in rows:
            assert source in figures, (code, source)


def test_report_auto_fills_indicator_values(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from django.utils import timezone

    from membership.models import Member

    Member.objects.create(full_name="A", status="active")
    _indicator("membership", name="Active members", auto_source="active_members")
    head = verified_client(make_staff(MEMBERSHIP, heads={"membership"}))
    head.post(P + "membership/reports/generate/", {"month": timezone.localdate().strftime("%Y-%m")})
    value = IndicatorValue.objects.get(indicator__name="Active members")
    assert value.value == 1


def test_executive_flags(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from datetime import timedelta

    from django.utils import timezone

    from development.models import Milestone, Project

    project = Project.objects.create(name="Hostel", kind="hostel")
    Milestone.objects.create(project=project, title="Roof", due_date=timezone.localdate() - timedelta(days=2))
    founder = verified_client(make_staff(superuser=True))
    html = founder.get(P + "executive/").content.decode()
    assert "milestone(s) overdue" in html and f'href="{P}development/projects/"' in html
    executive = verified_client(make_staff(EXECUTIVE))
    html = executive.get(P + "executive/").content.decode()
    assert "milestone(s) overdue" in html and f'href="{P}development/projects/"' not in html
