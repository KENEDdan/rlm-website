"""Decision 1: Executive Finance page shows summaries only; detail stays with Finance and the Founder."""

from __future__ import annotations

from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from accounts.roles import EXECUTIVE, FINANCE, MEDIA, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from finance.models import BudgetLine, Donor, LedgerEntry, Pledge
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
TODAY = timezone.localdate()
URL = P + "executive/finance/"


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


@pytest.fixture
def books():  # type: ignore[no-untyped-def]
    juba, yei = Branch.objects.get(slug="juba"), Branch.objects.get(slug="yei")
    BudgetLine.objects.create(year=TODAY.year, department=dept("missions"), category="travel", name="Trips",
                              amount=Decimal("1000"), status="approved", branch=juba)
    BudgetLine.objects.create(year=TODAY.year, department=dept("media"), category="media", name="Posters",
                              amount=Decimal("500"), status="approved", branch=yei)
    BudgetLine.objects.create(year=TODAY.year, department=dept("media"), category="media", name="Draft line",
                              amount=Decimal("9999"), status="draft")
    LedgerEntry.objects.create(kind="income", income_source="offering", amount=Decimal("3000"), date=TODAY,
                               description="Sunday offering SECRET-IN", status="posted", number="IN-1", branch=juba)
    LedgerEntry.objects.create(kind="expense", category="travel", amount=Decimal("400"), date=TODAY,
                               description="Bus to Kajo-Keji SECRET-OUT", counterparty="SECRET-PAYEE",
                               department=dept("missions"), status="posted", number="EX-1", branch=juba)
    LedgerEntry.objects.create(kind="expense", category="media", amount=Decimal("700"), date=TODAY,
                               description="Banners", department=dept("media"), status="posted", number="EX-2",
                               branch=yei)
    LedgerEntry.objects.create(kind="expense", category="media", amount=Decimal("50"), date=TODAY,
                               description="Unposted", department=dept("media"), status="submitted")
    donor = Donor.objects.create(name="SECRET-DONOR", email="donor@example.test")
    Pledge.objects.create(donor=donor, amount=Decimal("800"), received_amount=Decimal("300"))
    return juba, yei


def test_executive_sees_summaries(make_staff, verified_client, books) -> None:  # type: ignore[no-untyped-def]
    page = verified_client(make_staff(EXECUTIVE)).get(URL)
    assert page.status_code == 200
    d = page.context["data"]
    assert (d["income"], d["expenditure"], d["cash"]) == (Decimal("3000"), Decimal("1100"), Decimal("1900"))
    assert d["outstanding_pledges"] == Decimal("500")
    assert d["approved_budget"] == Decimal("1500")  # the draft line is not an approved budget
    media = next(r for r in d["by_department"] if r["code"] == "media")
    assert media["over"] and media["actual"] == Decimal("700")
    assert {r["label"] for r in d["by_branch"]} == {books[0].name, books[1].name}
    html = page.content.decode()
    for secret in ("SECRET-IN", "SECRET-OUT", "SECRET-PAYEE", "SECRET-DONOR", "donor@example.test", "EX-1", "IN-1"):
        assert secret not in html
    assert AuditLog.objects.filter(action=AuditLog.Action.VIEW, extra__page="executive finance").exists()


def test_drill_down_stops_at_categories(make_staff, verified_client, books) -> None:  # type: ignore[no-untyped-def]
    page = verified_client(make_staff(EXECUTIVE)).get(URL + "?department=missions")
    drill = page.context["data"]["drill"]
    assert drill["department"] and [r["label"] for r in drill["rows"]] == ["Travel & transport"]
    assert "SECRET-OUT" not in page.content.decode()


def test_branch_and_period_filters(make_staff, verified_client, books) -> None:  # type: ignore[no-untyped-def]
    juba, _yei = books
    client = verified_client(make_staff(EXECUTIVE))
    d = client.get(URL + f"?fy={TODAY.year}&branch={juba.pk}").context["data"]
    assert d["expenditure"] == Decimal("400") and d["income"] == Decimal("3000")
    other_month = 1 if TODAY.month != 1 else 2
    d = client.get(URL + f"?fy={TODAY.year}&period=m{other_month}").context["data"]
    assert d["expenditure"] == 0
    d = client.get(URL + f"?fy={TODAY.year - 1}").context["data"]
    assert d["approved_budget"] == 0


def test_executive_cannot_open_ledger_detail(make_staff, verified_client, books) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(EXECUTIVE))
    entry = LedgerEntry.objects.get(number="EX-1")
    for path in ("finance/ledger/", f"finance/ledger/{entry.pk}/", "finance/donors/", "finance/pledges/",
                 "finance/ledger/export/", "finance/donations/"):
        assert client.get(P + path).status_code in (403, 404), path


@pytest.mark.parametrize("role", [MEDIA, MEMBERSHIP])
def test_other_departments_cannot_see_executive_finance(make_staff, verified_client, role) -> None:  # type: ignore[no-untyped-def]
    assert verified_client(make_staff(role)).get(URL).status_code == 403


def test_finance_and_founder_see_it_too(make_staff, verified_client, books) -> None:  # type: ignore[no-untyped-def]
    assert verified_client(make_staff(FINANCE)).get(URL).status_code == 200
    assert verified_client(make_staff(superuser=True)).get(URL).status_code == 200
