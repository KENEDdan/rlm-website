"""Finance: segregation of duties, thresholds, immutable postings, reversals, budget isolation, pipeline."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone

from accounts.roles import BRANCH_COORDINATOR, FINANCE, MEDIA, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from finance.models import BudgetLine, Donor, FinanceVolunteer, LedgerEntry
from giving.models import Donation, PartnershipEnquiry
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


def _entry(user, **kw) -> LedgerEntry:  # type: ignore[no-untyped-def]
    data = {
        "kind": "expense",
        "amount": Decimal("200"),
        "category": "travel",
        "description": "Bus to Yei",
        "department": dept("missions"),
        "recorded_by": user,
        "status": "submitted",
    }
    data.update(kw)
    return LedgerEntry.objects.create(**data)


@pytest.fixture
def recorder(make_staff):  # type: ignore[no-untyped-def]
    return make_staff(FINANCE, email="recorder@example.test")


@pytest.fixture
def approver(make_staff):  # type: ignore[no-untyped-def]
    return make_staff(FINANCE, email="approver@example.test", heads={"finance"})


INCOME = {"kind": "income", "income_source": "offering", "category": ""}


def test_recorder_cannot_approve_own_entry(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    """Income: any Finance member except the recorder approves (expenditure: see test_approvals.py)."""
    entry = _entry(recorder, **INCOME)
    mine = verified_client(recorder)
    assert mine.post(P + f"finance/ledger/{entry.pk}/step/approve/").status_code == 302
    entry.refresh_from_db()
    assert entry.status == "submitted"
    other = verified_client(approver)
    other.post(P + f"finance/ledger/{entry.pk}/step/approve/")
    entry.refresh_from_db()
    assert entry.status == "posted" and entry.approved_by == approver and entry.number.startswith("IN-")
    assert AuditLog.objects.filter(action=AuditLog.Action.POST, object_id=str(entry.pk)).exists()


def test_recording_through_the_portal_then_submit(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(recorder)
    resp = client.post(
        P + "finance/ledger/new/",
        {
            "kind": "expense",
            "date": "2026-11-01",
            "amount": "50",
            "currency": "USD",
            "department": dept("media").pk,
            "category": "media",
            "description": "Posters",
        },
    )
    assert resp.status_code == 302
    entry = LedgerEntry.objects.get(description="Posters")
    assert entry.recorded_by == recorder and entry.status == "draft"
    client.post(P + f"finance/ledger/{entry.pk}/step/submit/")
    entry.refresh_from_db()
    assert entry.status == "submitted"
    # expenditure is never approved inside Finance: it goes to executive approval (decision 3)
    for client_ in (client, verified_client(approver)):
        assert b"Approve and post" not in client_.get(P + f"finance/ledger/{entry.pk}/").content
    verified_client(approver).post(P + f"finance/ledger/{entry.pk}/step/approve/")
    entry.refresh_from_db()
    assert entry.status == "submitted"


def test_expense_needs_category_income_needs_source(recorder, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(recorder)
    resp = client.post(
        P + "finance/ledger/new/",
        {"kind": "expense", "date": "2026-11-01", "amount": "5", "currency": "USD", "description": "x"},
    )
    assert resp.status_code == 200 and not LedgerEntry.objects.exists()
    resp = client.post(
        P + "finance/ledger/new/",
        {
            "kind": "income",
            "date": "2026-11-01",
            "amount": "-5",
            "currency": "USD",
            "description": "x",
            "income_source": "offering",
        },
    )
    assert resp.status_code == 200 and not LedgerEntry.objects.exists()


def test_posted_entries_are_immutable(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    entry = _entry(recorder, status="posted", approved_by=approver, number="EX-2026-00001")
    entry.description = "changed"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        LedgerEntry.objects.filter(pk=entry.pk).update(amount=1)
    with pytest.raises(PermissionError):
        LedgerEntry.objects.filter(pk=entry.pk).delete()
    head = verified_client(approver)
    assert head.get(P + f"finance/ledger/{entry.pk}/edit/").status_code == 403
    assert head.post(P + f"finance/ledger/{entry.pk}/delete/").status_code == 403


def test_reversal_flow(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    """Correcting posted income (a reversal of expenditure goes to executive approval, see test_approvals)."""
    entry = _entry(recorder, status="posted", approved_by=approver, number="IN-2026-00001", **INCOME)
    head = verified_client(approver)
    assert (
        verified_client(recorder)
        .post(P + f"finance/ledger/{entry.pk}/step/reverse/", {"note": "x"})
        .status_code
        == 403
    )
    head.post(P + f"finance/ledger/{entry.pk}/step/reverse/", {"note": ""})
    assert not LedgerEntry.objects.filter(reverses=entry).exists()
    head.post(P + f"finance/ledger/{entry.pk}/step/reverse/", {"note": "Wrong department"})
    mirror = LedgerEntry.objects.get(reverses=entry)
    assert (
        mirror.amount == Decimal("-200") and mirror.status == "submitted" and mirror.recorded_by == approver
    )
    head.post(P + f"finance/ledger/{mirror.pk}/step/approve/")  # the head recorded it -> cannot approve
    mirror.refresh_from_db()
    assert mirror.status == "submitted"
    verified_client(recorder).post(P + f"finance/ledger/{mirror.pk}/step/approve/")
    mirror.refresh_from_db()
    assert mirror.status == "posted" and mirror.number.startswith("RV-")
    head.post(P + f"finance/ledger/{entry.pk}/step/reverse/", {"note": "again"})
    assert LedgerEntry.objects.filter(reverses=entry).count() == 1


@pytest.mark.parametrize("role", [MEMBERSHIP, MEDIA, BRANCH_COORDINATOR])
def test_other_departments_never_see_ledgers_or_donors(role, make_staff, verified_client, recorder) -> None:  # type: ignore[no-untyped-def]
    entry = _entry(recorder)
    donor = Donor.objects.create(name="Secret Church")
    client = verified_client(make_staff(role, branch=Branch.objects.first()))
    for url in (
        "finance/",
        "finance/ledger/",
        f"finance/ledger/{entry.pk}/",
        "finance/donors/",
        f"finance/donors/{donor.pk}/",
        "finance/budget/",
        "finance/ledger/export.csv",
        f"finance/donors/{donor.pk}/accountability/",
    ):
        assert client.get(P + url).status_code == 403, url


def test_departments_see_only_their_own_budget_totals(make_staff, verified_client, recorder, approver) -> None:  # type: ignore[no-untyped-def]
    year = timezone.localdate().year
    media_line = BudgetLine.objects.create(
        year=year, department=dept("media"), category="media", name="Posters", amount=1000
    )
    BudgetLine.objects.create(
        year=year, department=dept("missions"), category="travel", name="Crusade travel", amount=5000
    )
    _entry(
        recorder,
        department=dept("media"),
        budget_line=media_line,
        category="media",
        amount=Decimal("250"),
        description="Secret supplier invoice",
        status="posted",
        approved_by=approver,
        number="EX-1",
    )
    client = verified_client(make_staff(MEDIA))
    page = client.get(P + "media/my-budget/")
    html = page.content.decode()
    assert page.status_code == 200
    assert "Posters" in html and "250.00" in html and "1000.00" in html
    assert "Crusade travel" not in html and "Secret supplier invoice" not in html
    assert client.get(P + "missions/my-budget/").status_code == 403
    assert client.get(P + "finance/budget/").status_code == 403


def test_branch_coordinator_has_no_budget_page(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=Branch.objects.first()))
    assert client.get(P + "membership/my-budget/").status_code == 403


def test_donation_confirmation_creates_income_for_someone_else_to_approve(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    donation = Donation.objects.create(
        amount=Decimal("75"), donor_name="Kind Giver", donor_email="g@example.test"
    )
    verified_client(recorder).post(P + f"finance/donations/{donation.pk}/confirm/")
    donation.refresh_from_db()
    entry = LedgerEntry.objects.get(donation=donation)
    assert donation.status == "confirmed" and entry.kind == "income" and entry.status == "submitted"
    assert entry.recorded_by == recorder
    verified_client(recorder).post(P + f"finance/ledger/{entry.pk}/step/approve/")
    entry.refresh_from_db()
    assert entry.status == "submitted"


def test_partnership_registration_feeds_donor_pipeline(recorder, verified_client) -> None:  # type: ignore[no-untyped-def]
    enquiry = PartnershipEnquiry.objects.create(
        partner_type="church",
        name="Pastor Ben",
        organisation="Grace Church",
        email="ben@example.test",
        country="Kenya",
        consent=True,
    )
    verified_client(recorder).post(P + f"finance/partner-registrations/{enquiry.pk}/to-donor/")
    donor = Donor.objects.get(source_enquiry=enquiry)
    assert donor.name == "Grace Church" and donor.kind == "church" and donor.stage == "prospect"
    with connection.cursor() as cur:
        cur.execute("SELECT name, email FROM finance_donor WHERE id=%s", [donor.pk])
        name, email = cur.fetchone()
    assert "Grace" not in name and "ben@" not in email


def test_finance_volunteer_vetting_never_grants_access(recorder, approver, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.models import User

    volunteer = FinanceVolunteer.objects.create(
        full_name="Ann",
        email="ann@example.test",
        phone="+211900000009",
        education_level="Degree",
        finance_experience="yes",
        statement="CPA",
        willing_integrity="yes",
        declaration=True,
    )
    clerk, head = verified_client(recorder), verified_client(approver)
    clerk.post(P + f"finance/volunteers/{volunteer.pk}/step/references/")
    clerk.post(P + f"finance/volunteers/{volunteer.pk}/step/interview/")
    volunteer.refresh_from_db()
    assert volunteer.status == "references"  # references must be recorded as checked first
    FinanceVolunteer.objects.filter(pk=volunteer.pk).update(references_checked=True)
    clerk.post(P + f"finance/volunteers/{volunteer.pk}/step/interview/")
    assert clerk.post(P + f"finance/volunteers/{volunteer.pk}/step/approve/").status_code == 403
    head.post(P + f"finance/volunteers/{volunteer.pk}/step/approve/")
    volunteer.refresh_from_db()
    assert volunteer.status == "approved"
    assert not User._base_manager.filter(email="ann@example.test").exists()


def test_finance_dashboard_and_exec_summary(approver, recorder, verified_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    _entry(
        recorder,
        kind="income",
        income_source="offering",
        category="",
        amount=Decimal("1000"),
        status="posted",
        approved_by=approver,
        number="IN-1",
    )
    _entry(recorder, amount=Decimal("300"), status="posted", approved_by=approver, number="EX-1")
    page = verified_client(approver).get(P + "finance/")
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert kpis["cash_position"] == "700.00"
    overview = verified_client(make_staff(superuser=True)).get(P + "executive/").content.decode()
    assert "700.00" in overview
