"""Decision 3: executive approval of every expenditure and commitment, the UNBUDGETED path, approvers."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.core import mail
from django.utils import timezone

from accounts.roles import FINANCE, LOGISTICS, MISSIONS
from audit.models import AuditLog
from finance.approvals import KINDS, check_budget, is_approver, line_position
from finance.models import (
    ApprovalDecision,
    Approver,
    BudgetAdjustment,
    BudgetLine,
    FinanceSettings,
    LedgerEntry,
)
from logistics.models import LogisticsPlan, PurchaseRequest
from missions.models import Campaign
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
YEAR = timezone.localdate().year


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


def _line(code: str = "missions", amount: int = 1000, status: str = "approved", **kw) -> BudgetLine:  # type: ignore[no-untyped-def]
    return BudgetLine.objects.create(
        year=YEAR,
        department=dept(code),
        category="travel",
        name=kw.pop("name", f"{code} travel"),
        amount=Decimal(amount),
        status=status,
        **kw,
    )


def _expense(recorder, line: BudgetLine | None = None, amount: int = 200, **kw) -> LedgerEntry:  # type: ignore[no-untyped-def]
    return LedgerEntry.objects.create(
        kind="expense",
        amount=Decimal(amount),
        category="travel",
        description="Bus hire",
        department=dept("missions"),
        budget_line=line,
        recorded_by=recorder,
        status="submitted",
        **kw,
    )


@pytest.fixture
def founder(make_staff, verified_client, reauth):  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True, email="founder@example.test")
    client = verified_client(user)
    reauth(client, user)
    return user, client


def test_expenditure_needs_executive_approval_not_finance(make_staff, verified_client, founder) -> None:  # type: ignore[no-untyped-def]
    recorder = make_staff(FINANCE, email="rec@example.test")
    head = make_staff(FINANCE, heads={"finance"}, email="head@example.test")
    entry = _expense(recorder, _line())
    verified_client(head).post(P + f"finance/ledger/{entry.pk}/step/approve/")
    entry.refresh_from_db()
    assert entry.status == "submitted"
    assert verified_client(head).get(P + f"approvals/expense/{entry.pk}/").status_code == 403
    user, client = founder
    client.post(P + f"approvals/expense/{entry.pk}/", {"decision": "approve"})
    entry.refresh_from_db()
    assert (
        entry.status == "posted"
        and entry.approved_by == user
        and entry.number.startswith("EX-")
        and not entry.unbudgeted
    )
    decision = ApprovalDecision.objects.get(object_id=entry.pk, kind="expense")
    assert decision.decision == "approved" and not decision.override and decision.approver == user
    assert AuditLog.objects.filter(
        action=AuditLog.Action.APPROVE, object_id=str(entry.pk), extra__executive_approval=True
    ).exists()


def test_requester_gets_an_email_without_sensitive_details(make_staff, founder, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    recorder = make_staff(FINANCE, email="rec@example.test")
    entry = _expense(recorder, _line(), amount=777)
    _user, client = founder
    with django_capture_on_commit_callbacks(execute=True):
        client.post(
            P + f"approvals/expense/{entry.pk}/",
            {"decision": "reject", "justification": "Use the cheaper bus"},
        )
    entry.refresh_from_db()
    assert entry.status == "rejected"
    message = next(m for m in mail.outbox if m.to == ["rec@example.test"])
    assert "NOT APPROVED" in message.body
    for secret in ("777", "Bus hire", "cheaper bus"):
        assert secret not in message.body and secret not in message.subject


def test_recorder_never_approves_even_as_approver(make_staff, verified_client, reauth) -> None:  # type: ignore[no-untyped-def]
    boss = make_staff(superuser=True)
    entry = _expense(boss, _line())
    client = verified_client(boss)
    reauth(client, boss)
    client.post(P + f"approvals/expense/{entry.pk}/", {"decision": "approve"})
    entry.refresh_from_db()
    assert entry.status == "submitted"


def test_approval_needs_reauthentication(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    boss = make_staff(superuser=True)
    entry = _expense(make_staff(FINANCE), _line())
    resp = verified_client(boss).post(P + f"approvals/expense/{entry.pk}/", {"decision": "approve"})
    assert resp.status_code == 302 and "/accounts/confirm/" in resp["Location"]
    entry.refresh_from_db()
    assert entry.status == "submitted"


def test_unbudgeted_needs_justification_and_is_recorded_as_override(make_staff, founder) -> None:  # type: ignore[no-untyped-def]
    recorder = make_staff(FINANCE)
    no_line = _expense(recorder, None)
    small = _line(amount=100, name="small")
    too_big = _expense(recorder, small, amount=150)
    draft_line = _expense(recorder, _line(status="draft", name="draft line"), amount=10)
    for entry in (no_line, too_big, draft_line):
        assert check_budget(KINDS["expense"], entry).unbudgeted
    _user, client = founder
    client.post(P + f"approvals/expense/{no_line.pk}/", {"decision": "approve", "justification": ""})
    no_line.refresh_from_db()
    assert no_line.status == "submitted"
    client.post(
        P + f"approvals/expense/{no_line.pk}/", {"decision": "approve", "justification": "Emergency repair"}
    )
    no_line.refresh_from_db()
    assert no_line.status == "posted" and no_line.unbudgeted
    decision = ApprovalDecision.objects.get(object_id=no_line.pk, kind="expense")
    assert decision.unbudgeted and decision.override and decision.justification == "Emergency repair"


def test_unbudgeted_with_required_adjustment(make_staff, founder) -> None:  # type: ignore[no-untyped-def]
    FinanceSettings.objects.update_or_create(pk=1, defaults={"unbudgeted_requires_adjustment": True})
    recorder = make_staff(FINANCE)
    small = _line(amount=100, name="small")
    donor_line = _line(code="media", amount=500, name="media spare")
    entry = _expense(recorder, small, amount=180)
    _user, client = founder
    client.post(P + f"approvals/expense/{entry.pk}/", {"decision": "approve", "justification": "Needed"})
    entry.refresh_from_db()
    assert entry.status == "submitted"  # an adjustment is required
    # reallocating from a line without enough balance is refused
    client.post(
        P + f"approvals/expense/{entry.pk}/",
        {
            "decision": "approve",
            "justification": "Needed",
            "adjustment": "reallocation",
            "from_line": donor_line.pk,
            "adjustment_amount": "900",
        },
    )
    entry.refresh_from_db()
    assert entry.status == "submitted"
    client.post(
        P + f"approvals/expense/{entry.pk}/",
        {
            "decision": "approve",
            "justification": "Needed",
            "adjustment": "reallocation",
            "from_line": donor_line.pk,
            "adjustment_amount": "80",
        },
    )
    entry.refresh_from_db()
    assert entry.status == "posted"
    adjustment = BudgetAdjustment.objects.get()
    assert (
        adjustment.from_line == donor_line
        and adjustment.to_line == small
        and adjustment.amount == Decimal("80")
    )
    assert line_position(donor_line).remaining == Decimal("420")
    with pytest.raises(PermissionError):
        adjustment.delete()


def test_commitments_reduce_the_remaining_balance(make_staff, founder) -> None:  # type: ignore[no-untyped-def]
    line = _line(amount=1000)
    campaign = Campaign.objects.create(
        title="Crusade",
        kind="crusade",
        start_date=timezone.localdate(),
        budget_request=Decimal("800"),
        budget_line=line,
        budget_status="approved",
    )
    assert line_position(line).committed == Decimal("800")
    recorder = make_staff(FINANCE)
    outside = _expense(recorder, line, amount=300)
    assert check_budget(KINDS["expense"], outside).unbudgeted  # 1000 - 800 committed = 200 left
    within_commitment = _expense(recorder, line, amount=300, campaign=campaign)
    assert not check_budget(
        KINDS["expense"], within_commitment
    ).unbudgeted  # paid from the approved campaign budget
    _user, client = founder
    client.post(P + f"approvals/expense/{within_commitment.pk}/", {"decision": "approve"})
    assert line_position(line).committed == Decimal("500") and line_position(line).spent == Decimal("300")


def test_approver_list_and_acting_dates(make_staff, verified_client, reauth) -> None:  # type: ignore[no-untyped-def]
    founder = make_staff(superuser=True)
    acting = make_staff(FINANCE, email="acting@example.test")
    assert is_approver(founder) and not is_approver(acting)  # no list yet: the Super Admin approves
    today = timezone.localdate()
    Approver.objects.create(
        user=acting, role="acting", starts_on=today + timedelta(days=1), ends_on=today + timedelta(days=9)
    )
    assert not is_approver(acting) and not is_approver(founder)  # once a list exists, only it counts
    assert is_approver(acting, on=today + timedelta(days=2))
    Approver.objects.create(user=founder, role="founder")
    assert is_approver(founder)


def test_only_super_admin_manages_approvers_with_reauth(make_staff, verified_client, reauth) -> None:  # type: ignore[no-untyped-def]
    head = verified_client(make_staff(FINANCE, heads={"finance"}))
    target = make_staff(FINANCE, email="ed@example.test")
    assert head.get(P + "finance/approvers/").status_code == 403
    assert (
        head.post(
            P + "finance/approvers/new/", {"user": target.pk, "role": "executive_director", "is_active": "on"}
        ).status_code
        == 403
    )
    founder_user = make_staff(superuser=True)
    founder = verified_client(founder_user)
    resp = founder.get(P + "finance/approvers/new/")
    assert resp.status_code == 302 and "/accounts/confirm/" in resp["Location"]
    reauth(founder, founder_user)
    founder.post(P + "finance/approvers/new/", {"user": target.pk, "role": "acting", "is_active": "on"})
    assert not Approver.objects.exists()  # an acting approver needs dates
    founder.post(
        P + "finance/approvers/new/", {"user": target.pk, "role": "executive_director", "is_active": "on"}
    )
    assert Approver.objects.get().user == target


def test_purchase_unbudgeted_path(make_staff, verified_client, founder) -> None:  # type: ignore[no-untyped-def]
    requester = make_staff(LOGISTICS)
    pr = PurchaseRequest.objects.create(
        title="Generator",
        requesting_department=dept("logistics"),
        description="x",
        status="recommended",
        requested_by=requester,
        estimated_cost=Decimal("900"),
    )
    finance = verified_client(make_staff(FINANCE))
    finance.post(P + f"finance/procurement/{pr.pk}/confirm-budget/", {"budget_line": ""})
    pr.refresh_from_db()
    assert pr.status == "budget_confirmed" and pr.unbudgeted
    page = verified_client(make_staff(FINANCE, heads={"finance"})).get(P + "finance/")
    assert {k.code: k.value for k in page.context["board"].kpis}["unbudgeted_waiting"].startswith("1 ")
    _user, client = founder
    assert b"UNBUDGETED" in client.get(P + "approvals/").content
    assert b"UNBUDGETED" in client.get(P + "executive/").content
    client.post(
        P + f"approvals/purchase/{pr.pk}/",
        {"decision": "approve", "justification": "Power cuts at the office"},
    )
    pr.refresh_from_db()
    assert pr.status == "approved"


def test_campaign_and_event_budgets(make_staff, verified_client, founder) -> None:  # type: ignore[no-untyped-def]
    line = _line()
    missions_user = make_staff(MISSIONS)
    client = verified_client(missions_user)
    campaign = Campaign.objects.create(
        title="Mission trip to Kajo-Keji",
        kind="mission_trip",
        start_date=timezone.localdate(),
        budget_request=Decimal("400"),
        budget_line=line,
    )
    data = {
        "title": campaign.title,
        "kind": "mission_trip",
        "start_date": campaign.start_date.isoformat(),
        "budget_request": "400",
        "budget_line": line.pk,
        "status": "in_progress",
    }
    resp = client.post(P + f"missions/campaigns/{campaign.pk}/edit/", data)
    assert resp.status_code == 200  # cannot go ahead before the budget is approved
    client.post(P + f"missions/campaigns/{campaign.pk}/submit-budget/")
    campaign.refresh_from_db()
    assert campaign.budget_status == "submitted"
    _user, founder_client = founder
    founder_client.post(P + f"approvals/campaign/{campaign.pk}/", {"decision": "approve"})
    campaign.refresh_from_db()
    assert campaign.budget_status == "approved" and campaign.status == "approved"
    plan = LogisticsPlan.objects.create(
        title="Youth conference",
        kind="conference",
        start_date=timezone.localdate(),
        budget_amount=Decimal("2000"),
    )
    verified_client(make_staff(LOGISTICS)).post(P + f"logistics/event-logistics/{plan.pk}/submit-budget/")
    plan.refresh_from_db()
    assert plan.budget_status == "submitted"
    assert check_budget(KINDS["event_budget"], plan).unbudgeted  # no budget line chosen
    founder_client.post(
        P + f"approvals/event_budget/{plan.pk}/",
        {"decision": "reject", "justification": "Choose a budget line"},
    )
    plan.refresh_from_db()
    assert plan.budget_status == "rejected" and plan.budget_decision_note == "Choose a budget line"


def test_budget_lines_need_executive_approval(make_staff, verified_client, founder) -> None:  # type: ignore[no-untyped-def]
    head_user = make_staff(FINANCE, heads={"finance"})
    head = verified_client(head_user)
    head.post(
        P + "finance/budget/new/",
        {
            "year": YEAR,
            "department": dept("media").pk,
            "category": "media",
            "name": "Posters",
            "amount": "300",
        },
    )
    line = BudgetLine.objects.get(name="Posters")
    assert line.status == "draft"
    head.post(P + f"finance/budget/{line.pk}/submit/")
    line.refresh_from_db()
    assert line.status == "submitted"
    assert head.get(P + f"finance/budget/{line.pk}/edit/").status_code == 403
    _user, client = founder
    client.post(P + f"approvals/budget_line/{line.pk}/", {"decision": "approve"})
    line.refresh_from_db()
    assert line.status == "approved" and head.get(P + f"finance/budget/{line.pk}/edit/").status_code == 403


def test_decisions_are_permanent() -> None:
    decision = ApprovalDecision.objects.create(
        kind="expense", object_id=1, reference="x", amount=1, decision="approved"
    )
    with pytest.raises(PermissionError):
        decision.save()
    with pytest.raises(PermissionError):
        decision.delete()
    with pytest.raises(PermissionError):
        ApprovalDecision.objects.all().update(amount=2)
    with pytest.raises(PermissionError):
        ApprovalDecision.objects.all().delete()


def test_no_threshold_setting_remains() -> None:
    assert not hasattr(FinanceSettings, "approval_threshold")
