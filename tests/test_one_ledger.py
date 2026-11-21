"""Decision 6: project, purchase-order and campaign money lives in ONE place, the Finance ledger."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from accounts.roles import DEVELOPMENT, FINANCE
from development.models import Milestone, Project
from finance.models import BudgetLine, LedgerEntry
from missions.models import Campaign
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
TODAY = timezone.localdate()


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


def _project(amount: int = 10000) -> Project:
    line = BudgetLine.objects.create(
        year=TODAY.year,
        department=dept("development"),
        category="construction",
        name="Hall",
        amount=Decimal(amount),
        status="approved",
    )
    return Project.objects.create(
        name="Hall",
        kind="hall",
        phase="construction",
        budget_line=line,
        start_date=TODAY - timedelta(days=30),
        target_end=TODAY + timedelta(days=90),
    )


@pytest.fixture
def founder(make_staff, verified_client, reauth):  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True, email="founder@example.test")
    client = verified_client(user)
    reauth(client, user)
    return client


def test_project_cost_is_one_ledger_entry_through_approval(make_staff, verified_client, founder) -> None:  # type: ignore[no-untyped-def]
    project = _project()
    dev_user = make_staff(DEVELOPMENT)
    dev = verified_client(dev_user)
    dev.post(
        P + "development/project-costs/new/",
        {"project": project.pk, "date": TODAY.isoformat(), "amount": "2500", "description": "Roofing sheets"},
    )
    entry = LedgerEntry.objects.get(description="Roofing sheets")
    assert (
        entry.kind,
        entry.status,
        entry.project,
        entry.budget_line,
        entry.department.code,
        entry.recorded_by,
    ) == ("expense", "draft", project, project.budget_line, "development", dev_user)
    dev.post(P + f"development/project-costs/{entry.pk}/submit/")
    entry.refresh_from_db()
    assert entry.status == "submitted" and project.committed == Decimal("2500") and project.spent == 0
    # Finance sees the very same entry (no second copy)
    finance = verified_client(make_staff(FINANCE))
    assert finance.get(P + f"finance/ledger/{entry.pk}/").status_code == 200
    founder.post(P + f"approvals/expense/{entry.pk}/", {"decision": "approve"})
    entry.refresh_from_db()
    assert entry.status == "posted"
    assert LedgerEntry.objects.filter(project=project).count() == 1
    summary = project.finance_summary()
    assert (
        summary["spent"] == Decimal("2500")
        and summary["committed"] == 0
        and summary["remaining"] == Decimal("7500")
    )
    # posted: Development can no longer edit or delete it
    assert dev.get(P + f"development/project-costs/{entry.pk}/edit/").status_code == 403


def test_development_sees_only_project_costs_not_the_ledger(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    project = _project()
    LedgerEntry.objects.create(
        kind="expense",
        amount=5,
        category="admin",
        description="Office rent",
        department=dept("finance"),
        status="posted",
        number="EX-9",
    )
    LedgerEntry.objects.create(
        kind="expense",
        amount=7,
        category="construction",
        description="Bricks",
        department=dept("development"),
        project=project,
        budget_line=project.budget_line,
        status="posted",
        number="EX-10",
    )
    dev = verified_client(make_staff(DEVELOPMENT))
    html = dev.get(P + "development/project-costs/").content.decode()
    assert "Bricks" in html and "Office rent" not in html
    assert dev.get(P + "finance/ledger/").status_code == 403


def test_project_dashboard_figures_and_alerts(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    project = _project(amount=1000)
    Milestone.objects.create(project=project, title="Walls", due_date=TODAY + timedelta(days=10))
    LedgerEntry.objects.create(
        kind="expense",
        amount=Decimal("1200"),
        category="construction",
        description="Steel",
        department=dept("development"),
        project=project,
        budget_line=project.budget_line,
        status="posted",
        number="EX-11",
        unbudgeted=True,
    )
    no_line = Project.objects.create(name="Hostel", kind="hostel", phase="construction")
    board = verified_client(make_staff(DEVELOPMENT)).get(P + "development/").context["board"]
    texts = [i.text for i in board.attention]
    assert any(t.startswith("Overspent: Hall") for t in texts)
    assert any(t.startswith("UNBUDGETED costs on Hall") for t in texts)
    assert any(t.startswith("Money ahead of progress: Hall") for t in texts)
    assert any(t == f"No budget line: {no_line}" for t in texts)
    page = verified_client(make_staff(DEVELOPMENT)).get(P + f"development/projects/{project.pk}/")
    assert b"Money (from the Finance ledger)" in page.content and b"Overspent" in page.content


def test_campaign_and_purchase_order_show_ledger_payments(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    line = BudgetLine.objects.create(
        year=TODAY.year,
        department=dept("missions"),
        category="outreach",
        name="Outreach",
        amount=1000,
        status="approved",
    )
    campaign = Campaign.objects.create(
        title="Crusade",
        kind="crusade",
        start_date=TODAY,
        budget_request=500,
        budget_line=line,
        budget_status="approved",
    )
    LedgerEntry.objects.create(
        kind="expense",
        amount=Decimal("300"),
        category="outreach",
        description="Sound hire",
        department=dept("missions"),
        campaign=campaign,
        budget_line=line,
        status="posted",
        number="EX-12",
    )
    from missions.portal_config import CampaignResource

    assert CampaignResource().spent(campaign) == "300.00"
    from finance.approvals import line_position

    assert line_position(line).committed == Decimal("200")  # 500 approved - 300 already paid


def test_development_cannot_edit_a_finance_draft_tagged_with_a_project(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    project = _project()
    finance_draft = LedgerEntry.objects.create(
        kind="expense",
        amount=Decimal("90"),
        category="construction",
        description="Finance preparing",
        department=dept("finance"),
        project=project,
        status="draft",
        recorded_by=make_staff(FINANCE),
    )
    dev_head = verified_client(make_staff(DEVELOPMENT, heads={"development"}))
    assert dev_head.get(P + f"development/project-costs/{finance_draft.pk}/edit/").status_code == 403
    assert dev_head.post(P + f"development/project-costs/{finance_draft.pk}/delete/").status_code == 403
    finance_draft.refresh_from_db()
    assert finance_draft.department.code == "finance"
