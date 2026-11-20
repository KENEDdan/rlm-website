"""Development & Infrastructure: projects, milestones, maintenance, Finance handoff, timeline."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from accounts.roles import DEVELOPMENT, FINANCE, MISSIONS
from development.models import (
    CapitalProposal,
    MaintenanceRequest,
    Milestone,
    Project,
    Property,
    SiteVisit,
)
from finance.models import BudgetLine, LedgerEntry, Proposal
from portal.charts import timeline
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def _project(**kw) -> Project:  # type: ignore[no-untyped-def]
    today = timezone.localdate()
    data = {
        "name": "Juba conference hall",
        "kind": "hall",
        "phase": "construction",
        "funding_secured": Decimal("60000"),
        "start_date": today - timedelta(days=60),
        "target_end": today + timedelta(days=120),
    }
    data.update(kw)
    if "budget_line" not in data:
        data["budget_line"] = BudgetLine.objects.create(
            year=today.year,
            department=Department.objects.get(code="development"),
            category="construction",
            name=data["name"],
            amount=Decimal("100000"),
            status="approved",
        )
    return Project.objects.create(**data)


def test_dashboard_kpis_and_timeline(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    project = _project()
    LedgerEntry.objects.create(
        kind="expense",
        status="posted",
        number="EX-1",
        amount=Decimal("25000"),
        category="construction",
        description="Foundation",
        project=project,
        department=Department.objects.get(code="development"),
        budget_line=project.budget_line,
    )
    Milestone.objects.create(
        project=project, title="Roof on", due_date=timezone.localdate() - timedelta(days=3)
    )
    SiteVisit.objects.create(project=project, progress_percent=35, summary="Walls up")
    MaintenanceRequest.objects.create(
        site=Property.objects.create(name="Juba office", kind="building", location="Juba"),
        title="Leaking roof",
        priority="urgent",
    )
    page = verified_client(make_staff(DEVELOPMENT)).get(P + "development/")
    board = page.context["board"]
    kpis = {k.code: k.value for k in board.kpis}
    assert (
        kpis["funding_gap"] == "40,000.00"
        and kpis["milestones_overdue"] == 1
        and kpis["maintenance_backlog"] == 1
    )
    assert board.timeline["rows"][0]["progress"] == 35 and board.timeline["rows"][0]["late"] is True
    html = page.content.decode()
    assert "Project timeline" in html and "Juba conference hall" in html
    assert any("Urgent maintenance" in i.text for i in board.attention)


def test_timeline_geometry() -> None:
    today = timezone.localdate()
    geo = timeline(
        [
            {
                "label": "A",
                "start": today - timedelta(days=10),
                "end": today + timedelta(days=10),
                "progress": 50,
            }
        ]
    )
    row = geo["rows"][0]
    assert row["x"] == 0 and row["w"] == 100 and row["done_w"] == 50 and 45 <= geo["today"] <= 55
    assert timeline([{"label": "undated", "start": None, "end": None}])["rows"] == []


def test_capital_proposal_goes_to_finance(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    proposal = CapitalProposal.objects.create(
        project=_project(), title="Hall phase 2", amount=Decimal("40000"), summary="Roof and floor"
    )
    member = verified_client(make_staff(DEVELOPMENT))
    assert member.post(P + f"development/capital-proposals/{proposal.pk}/send/").status_code == 403
    head = verified_client(make_staff(DEVELOPMENT, heads={"development"}))
    head.post(P + f"development/capital-proposals/{proposal.pk}/send/")
    proposal.refresh_from_db()
    assert proposal.status == "with_finance" and proposal.finance_proposal.amount_requested == Decimal(
        "40000"
    )
    finance = verified_client(make_staff(FINANCE))
    assert finance.get(P + f"finance/proposals/{proposal.finance_proposal.pk}/").status_code == 200
    head.post(P + f"development/capital-proposals/{proposal.pk}/send/")
    assert Proposal.objects.count() == 1


def test_development_records_isolated(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    project = _project()
    client = verified_client(make_staff(MISSIONS))
    for url in (
        "development/",
        "development/projects/",
        f"development/projects/{project.pk}/",
        "development/properties/",
    ):
        assert client.get(P + url).status_code == 403, url


def test_property_title_reference_encrypted() -> None:
    from django.db import connection

    prop = Property.objects.create(name="Plot 7", kind="land", location="Yei", title_reference="DEED-12345")
    with connection.cursor() as cur:
        cur.execute("SELECT title_reference FROM development_property WHERE id=%s", [prop.pk])
        assert "DEED" not in cur.fetchone()[0]
