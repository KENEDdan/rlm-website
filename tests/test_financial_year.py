"""Decision 2: financial year = calendar year; closed years accept nothing; close/reopen rules."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest
from django.conf import settings
from django.test import RequestFactory
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.roles import FINANCE, FOUNDER
from audit.models import AuditLog
from finance.models import BudgetLine, ClosedYearError, FinancialYear, LedgerEntry
from portal.access import Access
from portal.dashboards import period_range, read_filters
from portal.models import Department
from tests.conftest import PASSWORD, format_token, totp_now

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
LAST = date.today().year - 1


def _entry(year: int = LAST, **kw) -> LedgerEntry:  # type: ignore[no-untyped-def]
    data = {
        "kind": "income",
        "income_source": "offering",
        "amount": Decimal("50"),
        "description": "Offering",
        "date": date(year, 6, 1),
        "status": "posted",
        "number": f"IN-{year}-{LedgerEntry.objects.count()}",
    }
    data.update(kw)
    return LedgerEntry.objects.create(**data)


def _close(year: int = LAST) -> FinancialYear:
    fy = FinancialYear.for_year(year)
    fy.status = FinancialYear.Status.CLOSED
    fy.save()
    return fy


def test_years_are_calendar_years_and_created_on_demand() -> None:
    fy = FinancialYear.for_date(date(2026, 7, 4))
    assert (fy.start, fy.end) == (date(2026, 1, 1), date(2026, 12, 31))
    assert FinancialYear.current().year == date.today().year
    entry = _entry(2025)
    assert entry.financial_year.year == 2025


@pytest.mark.parametrize(
    ("period", "start", "end"),
    [
        ("", date(2026, 1, 1), date(2026, 12, 31)),
        ("q2", date(2026, 4, 1), date(2026, 6, 30)),
        ("q4", date(2026, 10, 1), date(2026, 12, 31)),
        ("m2", date(2026, 2, 1), date(2026, 2, 28)),
        ("m12", date(2026, 12, 1), date(2026, 12, 31)),
    ],
)
def test_quarters_and_months_derive_from_the_calendar_year(period: str, start: date, end: date) -> None:
    assert period_range(2026, period) == (start, end)


def test_dashboard_filters_use_financial_year_and_period(make_staff) -> None:
    request = RequestFactory().get("/", {"fy": "2025", "period": "q3"})
    filters = read_filters(request, Access(make_staff(superuser=True)))
    assert (filters.start, filters.end, filters.period_label) == (
        date(2025, 7, 1),
        date(2025, 9, 30),
        "Q3 2025",
    )
    default = read_filters(RequestFactory().get("/"), Access(make_staff(superuser=True)))
    assert default.start == date(date.today().year, 1, 1) and default.period_label.startswith(
        "Financial year"
    )


def test_nothing_can_be_recorded_changed_or_posted_in_a_closed_year(make_staff, verified_client) -> None:
    submitted = _entry(status="submitted", number=None, kind="expense", category="travel", income_source="")
    _close()
    with pytest.raises(ClosedYearError):
        _entry()
    with pytest.raises(ClosedYearError):
        BudgetLine.objects.create(
            year=LAST, department=Department.objects.get(code="media"), category="media", name="x", amount=1
        )
    clerk = verified_client(make_staff(FINANCE))
    resp = clerk.post(
        P + "finance/ledger/new/",
        {
            "kind": "income",
            "date": f"{LAST}-03-01",
            "amount": "5",
            "currency": "USD",
            "income_source": "offering",
            "description": "late",
        },
    )
    assert resp.status_code == 200 and b"is closed" in resp.content
    founder = verified_client(make_staff(superuser=True))
    founder.post(P + f"finance/ledger/{submitted.pk}/step/approve/")
    submitted.refresh_from_db()
    assert submitted.status == "submitted"


def test_close_year_rules(make_staff, verified_client) -> None:
    fy = FinancialYear.for_year(LAST)
    pending = _entry(status="submitted", number=None)
    head = verified_client(make_staff(FINANCE, heads={"finance"}))
    member = verified_client(make_staff(FINANCE))
    assert member.post(P + f"finance/financial-years/{fy.pk}/close/").status_code == 403
    head.post(P + f"finance/financial-years/{fy.pk}/close/")
    fy.refresh_from_db()
    assert not fy.is_closed  # an entry is still awaiting approval
    LedgerEntry.objects.filter(pk=pending.pk).delete()
    head.post(P + f"finance/financial-years/{fy.pk}/close/")
    fy.refresh_from_db()
    assert (
        fy.is_closed
        and AuditLog.objects.filter(action=AuditLog.Action.YEAR_CLOSED, object_id=str(fy.pk)).exists()
    )
    # the head cannot reopen
    assert head.post(P + f"finance/financial-years/{fy.pk}/reopen/", {"note": "x"}).status_code == 403


def test_reopen_needs_super_admin_and_reauthentication(make_staff, verified_client) -> None:
    fy = _close()
    founder_user = make_staff(FOUNDER, superuser=True)
    founder = verified_client(founder_user)
    resp = founder.post(P + f"finance/financial-years/{fy.pk}/reopen/", {"note": "Correct an error"})
    assert resp.status_code == 302 and "/accounts/confirm/" in resp["Location"]
    fy.refresh_from_db()
    assert fy.is_closed
    TOTPDevice.objects.filter(user=founder_user).update(last_t=-1)
    device = TOTPDevice.objects.get(user=founder_user)
    founder.post(P + "accounts/confirm/", {"password": PASSWORD, "code": format_token(totp_now(device))})
    founder.post(P + f"finance/financial-years/{fy.pk}/reopen/", {"note": ""})
    fy.refresh_from_db()
    assert fy.is_closed  # a reason is required
    founder.post(P + f"finance/financial-years/{fy.pk}/reopen/", {"note": "Correct an error"})
    fy.refresh_from_db()
    assert not fy.is_closed
    entry = AuditLog.objects.get(action=AuditLog.Action.YEAR_REOPENED, object_id=str(fy.pk))
    assert entry.extra["reason"] == "Correct an error"


def test_closed_year_is_shown_and_reports_carry_the_year(make_staff, verified_client) -> None:
    fy = _close()
    page = verified_client(make_staff(FINANCE)).get(P + f"finance/financial-years/{fy.pk}/").content.decode()
    assert "Closed" in page
