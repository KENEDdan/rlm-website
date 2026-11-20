"""Decision 4: monthly performance targets: split, adjustments with history, actuals, RAG, overdue, CSV import."""

from __future__ import annotations

import datetime as dt
from decimal import Decimal

import pytest
from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts.roles import EXECUTIVE, MEDIA, MISSIONS
from branches.models import Branch
from portal import indicators as svc
from portal.models import Department, Indicator, IndicatorValue, TargetChange

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
YEAR = timezone.localdate().year


def _target(**kw) -> Indicator:  # type: ignore[no-untyped-def]
    data = {
        "department": Department.objects.get(code="missions"),
        "category": "evangelism",
        "name": "Souls won",
        "year": YEAR,
        "annual_target": Decimal("1000"),
    }
    data.update(kw)
    indicator = Indicator.objects.create(**data)
    svc.ensure_monthly(indicator)
    return indicator


def test_annual_target_split_and_percent_levels() -> None:
    souls = _target()
    months = souls.monthly_map()
    assert months[1] == Decimal("83.33") and months[12] == Decimal("1000") - Decimal("83.33") * 11
    assert sum(months.values()) == Decimal("1000")
    rate = _target(name="Follow-up", unit="percent", annual_target=Decimal("60"))
    assert set(rate.monthly_map().values()) == {Decimal("60")}
    assert rate.target_for(dt.date(YEAR, 1, 1), "quarterly") == Decimal("60")
    assert souls.target_for(dt.date(YEAR, 1, 1), "quarterly") == Decimal("249.99")


def test_rag_rule() -> None:
    assert (svc.rag(95), svc.rag(90), svc.rag(89), svc.rag(70), svc.rag(69), svc.rag(None)) == (
        "green",
        "green",
        "amber",
        "amber",
        "red",
        "",
    )
    backlog = _target(name="Backlog", higher_is_better=False, annual_target=Decimal("120"))
    assert backlog.progress(Decimal("5"), Decimal("10")) == 100
    assert backlog.progress(Decimal("20"), Decimal("10")) == 50


def test_status_ytd_trend_and_overdue() -> None:
    souls = _target(annual_target=Decimal("1200"))
    Indicator.objects.filter(pk=souls.pk).update(created_at=timezone.make_aware(dt.datetime(YEAR, 1, 1)))
    souls.refresh_from_db()
    IndicatorValue.objects.create(indicator=souls, period_start=dt.date(YEAR, 1, 1), value=Decimal("100"))
    IndicatorValue.objects.create(indicator=souls, period_start=dt.date(YEAR, 2, 1), value=Decimal("50"))
    row = svc.status(souls, 3, today=dt.date(YEAR, 4, 11))
    assert row.ytd_target == Decimal("300") and row.ytd_actual == Decimal("150") and row.progress == 50
    assert row.rag == "red" and row.trend[:3] == [Decimal("100"), Decimal("50"), None]
    assert row.overdue == [3]  # March missing after 10 April
    assert svc.status(souls, 3, today=dt.date(YEAR, 4, 10)).overdue == []  # still within the grace days


def test_leadership_adjusts_with_history_departments_cannot(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    souls = _target()
    missions = verified_client(make_staff(MISSIONS, heads={"missions"}))
    missions.post(
        P + f"targets/{souls.pk}/", {"action": "annual", "annual_target": "5000", "reason": "Because"}
    )
    souls.refresh_from_db()
    assert souls.annual_target == Decimal("1000")
    exec_user = make_staff(EXECUTIVE)
    leader = verified_client(exec_user)
    leader.post(P + f"targets/{souls.pk}/", {"action": "annual", "annual_target": "1200", "reason": ""})
    souls.refresh_from_db()
    assert souls.annual_target == Decimal("1000")  # a reason is required
    leader.post(
        P + f"targets/{souls.pk}/", {"action": "annual", "annual_target": "1200", "reason": "Board raised it"}
    )
    souls.refresh_from_db()
    assert souls.annual_target == Decimal("1200") and souls.monthly_map()[1] == Decimal("100")
    change = TargetChange.objects.get(indicator=souls, month=None)
    assert (change.old_value, change.new_value, change.reason, change.changed_by) == (
        Decimal("1000"),
        Decimal("1200"),
        "Board raised it",
        exec_user,
    )
    leader.post(P + f"targets/{souls.pk}/", {"action": "months", "m12": "300", "reason": "Christmas crusade"})
    souls.refresh_from_db()
    assert souls.monthly_map()[12] == Decimal("300") and souls.annual_target == Decimal("1400")
    assert TargetChange.objects.filter(indicator=souls, month=12, old_value=Decimal("100")).exists()
    with pytest.raises(PermissionError):
        change.delete()
    page = leader.get(P + f"targets/{souls.pk}/").content.decode()
    assert "Christmas crusade" in page and "Board raised it" in page


def test_department_records_actuals_within_scope(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    juba, yei = Branch.objects.get(slug="juba"), Branch.objects.get(slug="yei")
    juba_target = _target(name="Juba souls", branch=juba)
    yei_target = _target(name="Yei souls", branch=yei)
    juba_staff = verified_client(make_staff(MISSIONS, scoped={"missions": juba}))
    assert juba_staff.get(P + f"targets/{yei_target.pk}/").status_code == 404
    juba_staff.post(P + f"targets/{juba_target.pk}/", {"action": "actual", "month": "1", "value": "70"})
    assert IndicatorValue.objects.get(indicator=juba_target).value == Decimal("70")
    future = timezone.localdate().month + 1
    if future <= 12:
        juba_staff.post(
            P + f"targets/{juba_target.pk}/", {"action": "actual", "month": str(future), "value": "5"}
        )
        assert not IndicatorValue.objects.filter(indicator=juba_target, period_start__month=future).exists()
    media = verified_client(make_staff(MEDIA))
    assert media.get(P + f"targets/{juba_target.pk}/").status_code == 404
    media.post(P + f"targets/{juba_target.pk}/", {"action": "actual", "month": "2", "value": "9"})
    assert IndicatorValue.objects.filter(indicator=juba_target).count() == 1


CSV_OK = (
    "category,name,unit,department,branch,year,annual_target,higher_is_better,"
    "jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec\n"
    f"evangelism,Souls won,number,missions,,{YEAR},1200,yes,,,,,,,,,,,,\n"
    f"prayer,Prayer nights,number,discipleship,juba,{YEAR},24,yes,2,2,2,2,2,2,2,2,2,2,2,2\n"
)


def test_csv_import_validates_previews_and_imports(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    leader = verified_client(make_staff(superuser=True))
    bad = CSV_OK + f"nonsense,X,number,missions,,{YEAR},abc,yes,,,,,,,,,,,,\n"
    resp = leader.post(P + "targets/import/", {"file": SimpleUploadedFile("t.csv", bad.encode(), "text/csv")})
    assert resp.context["result"].errors and not Indicator.objects.exists()  # all or nothing
    resp = leader.post(
        P + "targets/import/", {"file": SimpleUploadedFile("t.csv", CSV_OK.encode(), "text/csv")}
    )
    assert len(resp.context["result"].preview) == 2 and not Indicator.objects.exists()  # preview first
    leader.post(P + "targets/import/", {"confirm": "1"})
    assert Indicator.objects.count() == 2
    prayer = Indicator.objects.get(name="Prayer nights")
    assert prayer.branch.slug == "juba" and prayer.monthly_targets.count() == 12
    # importing again with a new figure updates and records the change
    changed = CSV_OK.replace(",1200,", ",1500,")
    leader.post(P + "targets/import/", {"file": SimpleUploadedFile("t.csv", changed.encode(), "text/csv")})
    leader.post(P + "targets/import/", {"confirm": "1"})
    souls = Indicator.objects.get(name="Souls won")
    assert souls.annual_target == Decimal("1500")
    assert TargetChange.objects.filter(
        indicator=souls, old_value=Decimal("1200"), new_value=Decimal("1500")
    ).exists()


@pytest.mark.parametrize(
    ("line", "message"),
    [
        (f"evangelism,X,number,missions,,{YEAR},-5,yes", "between 0"),
        (f"evangelism,X,number,missions,Nairobi-x,{YEAR},5,yes", "branch"),
        ("evangelism,X,number,missions,,20,5,yes", "year"),
        (f"evangelism,X,litres,missions,,{YEAR},5,yes", "unit"),
        (f"evangelism,X,number,nowhere,,{YEAR},5,yes", "department"),
        (f"evangelism,X,number,missions,,{YEAR},12,yes,1,1,1,1,1,1,1,1,1,1,1,9", "add up"),
        (f"evangelism,X,number,missions,,{YEAR},12,yes,1,1", "twelve"),
    ],
)
def test_csv_row_errors(line: str, message: str) -> None:
    header = "category,name,unit,department,branch,year,annual_target,higher_is_better,jan,feb,mar,apr,may,jun,jul,aug,sep,oct,nov,dec\n"
    _rows, errors = svc.parse_csv((header + line + "\n").encode())
    assert any(message in e for e in errors), errors


def test_csv_import_is_leadership_only(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    head = verified_client(make_staff(MISSIONS, heads={"missions"}))
    assert head.get(P + "targets/import/").status_code == 403
    assert head.get(P + "targets/template.csv").status_code == 403


def test_executive_overview_shows_every_category_and_overdue(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    souls = _target()
    Indicator.objects.filter(pk=souls.pk).update(created_at=timezone.make_aware(dt.datetime(YEAR, 1, 1)))
    page = verified_client(make_staff(EXECUTIVE)).get(P + "executive/")
    targets = page.context["overview"]["targets"]
    assert [c["code"] for c in targets["categories"]] == list(Indicator.Category.values)
    html = page.content.decode()
    for label in Indicator.Category.labels:
        assert label in html
    if timezone.localdate() > dt.date(YEAR, 2, 10):
        assert targets["overdue"] and "Overdue actuals" in html
