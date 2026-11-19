"""Missions & Outreach and Discipleship: handoff, pastoral notes, minors, branch scoping, dashboards."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.db import connection
from django.utils import timezone

from accounts.roles import BRANCH_COORDINATOR, DISCIPLESHIP, MEMBERSHIP, MISSIONS
from audit.models import AuditLog
from branches.models import Branch
from discipleship.models import Cohort, Disciple, Enrollment, FollowUp, PastoralNote, Registration
from missions.models import Campaign, FieldReport, NewConvert

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


@pytest.fixture
def juba() -> Branch:
    return Branch.objects.get(slug="juba")


@pytest.fixture
def yei() -> Branch:
    return Branch.objects.get(slug="yei")


def _campaign(branch: Branch, **kw) -> Campaign:  # type: ignore[no-untyped-def]
    return Campaign.objects.create(
        title=kw.pop("title", "Juba crusade"),
        kind="crusade",
        branch=branch,
        start_date=timezone.localdate(),
        **kw,
    )


def test_new_convert_is_handed_to_discipleship(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    campaign = _campaign(juba)
    missions = verified_client(make_staff(MISSIONS))
    resp = missions.post(
        P + "missions/converts/new/",
        {
            "campaign": campaign.pk,
            "decision_date": timezone.localdate().isoformat(),
            "full_name": "John Lado",
            "phone": "+211 922 000 111",
            "gender": "male",
            "age_band": "26_35",
            "location": "Gudele",
            "consent_to_contact": "on",
        },
    )
    assert resp.status_code == 302
    convert = NewConvert.objects.get()
    follow = FollowUp.objects.get(convert=convert)
    assert (
        follow.status == "new"
        and follow.branch == juba
        and follow.due_date == convert.decision_date + timedelta(days=7)
    )
    assert AuditLog.objects.filter(action=AuditLog.Action.HANDOFF, object_id=str(follow.pk)).exists()
    # Discipleship works it through to enrolment
    disc = verified_client(make_staff(DISCIPLESHIP))
    cohort = Cohort.objects.create(
        name="Foundations Juba", branch=juba, start_date=timezone.localdate(), status="running"
    )
    disc.post(P + f"discipleship/follow-ups/{follow.pk}/step/contacted/")
    disc.post(P + f"discipleship/follow-ups/{follow.pk}/step/enroll/", {"cohort": cohort.pk})
    follow.refresh_from_db()
    assert follow.status == "enrolled" and follow.disciple.full_name == "John Lado"
    assert Enrollment.objects.filter(cohort=cohort, disciple=follow.disciple).exists()
    # Missions sees the handoff status on its own record
    page = missions.get(P + f"missions/converts/{convert.pk}/").content.decode()
    assert "Enrolled in discipleship" in page
    # Executive overview shows the cross-department handoff
    founder = verified_client(make_staff(superuser=True))
    assert "Missions → Discipleship" in founder.get(P + "executive/").content.decode()


def test_missions_staff_cannot_open_discipleship_records(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    convert = NewConvert.objects.create(full_name="X", campaign=_campaign(juba))
    follow = convert.follow_up
    missions = verified_client(make_staff(MISSIONS))
    assert missions.get(P + f"discipleship/follow-ups/{follow.pk}/").status_code == 403
    assert missions.post(P + f"discipleship/follow-ups/{follow.pk}/step/contacted/").status_code == 403


def test_pastoral_notes_only_for_mentor_head_and_founder(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    mentor = make_staff(DISCIPLESHIP, email="mentor@example.test")
    other = make_staff(DISCIPLESHIP, email="other@example.test")
    head = make_staff(DISCIPLESHIP, email="head@example.test", heads={"discipleship"})
    disciple = Disciple.objects.create(full_name="Mary", mentor=mentor)
    note = PastoralNote.objects.create(disciple=disciple, author=mentor, note="Struggling with grief")
    with connection.cursor() as cur:
        cur.execute("SELECT note FROM discipleship_pastoralnote WHERE id=%s", [note.pk])
        assert "grief" not in cur.fetchone()[0]
    m, o, h = verified_client(mentor), verified_client(other), verified_client(head)
    f = verified_client(make_staff(superuser=True))
    url = P + f"discipleship/pastoral-notes/{note.pk}/"
    assert b"grief" in m.get(url).content
    assert o.get(url).status_code == 404
    assert b"grief" not in o.get(P + "discipleship/pastoral-notes/").content
    assert b"grief" not in o.get(P + f"discipleship/disciples/{disciple.pk}/").content
    assert b"grief" in h.get(url).content and f.get(url).status_code == 200
    assert o.get(P + "discipleship/pastoral-notes/export.csv").status_code == 403
    assert h.get(P + "discipleship/pastoral-notes/export.csv").status_code == 403  # never exported
    # every view is audited
    assert AuditLog.objects.filter(action=AuditLog.Action.VIEW, model="pastoralnote").count() >= 3
    # another member cannot write a note on someone else's mentee
    o.post(P + "discipleship/pastoral-notes/new/", {"disciple": disciple.pk, "note": "x"})
    assert PastoralNote.objects.count() == 1
    # and only the author can edit
    assert h.get(url + "edit/").status_code == 403
    assert m.get(url + "edit/").status_code == 200


def test_branch_coordinator_never_sees_pastoral_notes(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    disciple = Disciple.objects.create(full_name="Mary", branch=juba)
    note = PastoralNote.objects.create(disciple=disciple, note="private")
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))
    assert client.get(P + "discipleship/").status_code == 200
    assert client.get(P + "discipleship/pastoral-notes/").status_code == 403
    assert client.get(P + f"discipleship/pastoral-notes/{note.pk}/").status_code == 403


def test_minor_registrations_hidden_and_need_guardian(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    minor = Registration.objects.create(
        full_name="Teen",
        age="15",
        phone="1",
        born_again="yes",
        baptized="no",
        attends_church="yes",
        journey="x",
        consent=True,
    )
    assert minor.is_minor
    member = verified_client(make_staff(DISCIPLESHIP))
    head = verified_client(make_staff(DISCIPLESHIP, heads={"discipleship"}))
    assert member.get(P + f"discipleship/registrations/{minor.pk}/").status_code == 404
    assert head.get(P + f"discipleship/registrations/{minor.pk}/").status_code == 200
    head.post(P + f"discipleship/registrations/{minor.pk}/enroll/")
    minor.refresh_from_db()
    assert minor.status == "submitted"
    Registration.objects.filter(pk=minor.pk).update(guardian_consent=True)
    minor.refresh_from_db()
    minor.guardian_contact = "+211 900 111 222"
    minor.save()
    head.post(P + f"discipleship/registrations/{minor.pk}/enroll/")
    minor.refresh_from_db()
    assert minor.status == "enrolled" and minor.disciple.is_minor


def test_minor_converts_hidden_from_non_heads(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    convert = NewConvert.objects.create(
        full_name="Child", age_band="under_18", campaign=_campaign(juba), guardian_contact="x"
    )
    assert convert.follow_up.is_minor
    assert (
        verified_client(make_staff(MISSIONS)).get(P + f"missions/converts/{convert.pk}/").status_code == 404
    )
    assert (
        verified_client(make_staff(DISCIPLESHIP))
        .get(P + f"discipleship/follow-ups/{convert.follow_up.pk}/")
        .status_code
        == 404
    )
    assert (
        verified_client(make_staff(DISCIPLESHIP, heads={"discipleship"}))
        .get(P + f"discipleship/follow-ups/{convert.follow_up.pk}/")
        .status_code
        == 200
    )


def test_convert_form_requires_guardian_for_minor(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MISSIONS))
    client.post(
        P + "missions/converts/new/",
        {"decision_date": "2026-11-01", "full_name": "Kid", "age_band": "under_18"},
    )
    assert not NewConvert.objects.exists()


def test_branch_coordinator_scoped_in_missions(make_staff, verified_client, juba, yei) -> None:  # type: ignore[no-untyped-def]
    mine, other = _campaign(juba, title="Juba open air"), _campaign(yei, title="Yei crusade")
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))
    listing = client.get(P + "missions/campaigns/").content.decode()
    assert "Juba open air" in listing and "Yei crusade" not in listing
    assert client.get(P + f"missions/campaigns/{other.pk}/").status_code == 404
    # coordinators may file field reports for their own branch only
    resp = client.post(
        P + "missions/field-reports/new/",
        {"campaign": other.pk, "report_date": "2026-11-01", "souls_reached": 5, "decisions": 1},
    )
    assert resp.status_code == 200 and not FieldReport.objects.exists()
    client.post(
        P + "missions/field-reports/new/",
        {"campaign": mine.pk, "report_date": "2026-11-01", "souls_reached": 50, "decisions": 7},
    )
    assert FieldReport.objects.get().decisions == 7
    assert client.get(P + "missions/campaigns/new/").status_code == 403


def test_missions_dashboard_kpis(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    campaign = _campaign(juba, status="completed")
    FieldReport.objects.create(campaign=campaign, souls_reached=300, decisions=40)
    convert = NewConvert.objects.create(full_name="A", campaign=campaign)
    NewConvert.objects.create(full_name="B", campaign=campaign)
    FollowUp.objects.filter(convert=convert).update(status="enrolled")
    page = verified_client(make_staff(MISSIONS, heads={"missions"})).get(P + "missions/")
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert kpis["people_reached"] == 300 and kpis["decisions"] == 40 and kpis["follow_up_rate"] == "50%"
    assert any("Impact by location" in s["title"] for s in page.context["board"].sections)


def test_discipleship_dashboard(make_staff, verified_client, juba) -> None:  # type: ignore[no-untyped-def]
    NewConvert.objects.create(
        full_name="A", campaign=_campaign(juba), decision_date=timezone.localdate() - timedelta(days=30)
    )
    page = verified_client(make_staff(DISCIPLESHIP)).get(P + "discipleship/")
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert kpis["awaiting_follow_up"] == 1
    assert any("Overdue first contact" in i.text for i in page.context["board"].attention)


def test_other_departments_blocked(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEMBERSHIP, heads={"membership"}))
    for url in (
        "missions/",
        "missions/converts/",
        "discipleship/",
        "discipleship/pastoral-notes/",
        "discipleship/disciples/",
    ):
        assert client.get(P + url).status_code == 403, url
