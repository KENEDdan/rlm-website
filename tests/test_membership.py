"""Membership Administration: register, workflow, minors rule, branch scoping, engagement, messages."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.db import connection
from django.utils import timezone

from accounts.roles import BRANCH_COORDINATOR, FINANCE, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from membership.models import Activity, BulkMessage, Member
from portal.models import DepartmentReport

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def _member(**kw) -> Member:  # type: ignore[no-untyped-def]
    defaults = {
        "full_name": "Grace Akello",
        "email": "grace@example.test",
        "phone": "+211 900 000 001",
        "date_of_birth": "1995-04-02",
        "gender": "female",
        "testimony": "I gave my life to Christ in 2015.",
        "status": Member.Status.SUBMITTED,
        "branch": Branch.objects.get(slug="juba"),
    }
    defaults.update(kw)
    return Member.objects.create(**defaults)


@pytest.fixture
def head(make_staff, verified_client):  # type: ignore[no-untyped-def]
    return verified_client(make_staff(MEMBERSHIP, heads={"membership"}))


@pytest.fixture
def clerk(make_staff, verified_client):  # type: ignore[no-untyped-def]
    return verified_client(make_staff(MEMBERSHIP))


def test_sensitive_fields_are_encrypted_at_rest() -> None:
    member = _member()
    with connection.cursor() as cur:
        cur.execute(
            "SELECT full_name, email, phone, date_of_birth, testimony FROM membership_member WHERE id=%s",
            [member.pk],
        )
        row = cur.fetchone()
    for raw, plain in zip(
        row, ["Grace Akello", "grace@example.test", "+211 900", "1995-04-02", "Christ"], strict=True
    ):
        assert plain not in raw and raw.startswith("gAAAAA")
    member.refresh_from_db()
    assert member.full_name == "Grace Akello" and member.age_band == "26_35" and not member.is_minor


def test_approval_is_head_only_assigns_number_and_emails(head, clerk, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    member = _member()
    assert clerk.post(P + f"membership/members/{member.pk}/step/approve/").status_code == 403
    assert clerk.post(P + f"membership/members/{member.pk}/step/review/").status_code == 302
    member.refresh_from_db()
    assert member.status == "under_review" and member.member_number is None
    with django_capture_on_commit_callbacks(execute=True):
        assert head.post(P + f"membership/members/{member.pk}/step/approve/").status_code == 302
    member.refresh_from_db()
    assert member.status == "approved" and member.member_number == f"RLM-{member.pk:06d}" and member.join_date
    assert len(mail.outbox) == 1 and mail.outbox[0].to == ["grace@example.test"]
    assert "Christ" not in mail.outbox[0].body  # nothing they wrote is repeated
    assert AuditLog.objects.filter(action=AuditLog.Action.APPROVE, object_id=str(member.pk)).exists()


def test_reject_needs_private_reason(head) -> None:  # type: ignore[no-untyped-def]
    member = _member()
    head.post(P + f"membership/members/{member.pk}/step/reject/", {"note": ""})
    member.refresh_from_db()
    assert member.status == "submitted"
    head.post(P + f"membership/members/{member.pk}/step/reject/", {"note": "Duplicate"})
    member.refresh_from_db()
    assert member.status == "rejected" and member.member_number is None


def test_invalid_transition_refused(head) -> None:  # type: ignore[no-untyped-def]
    member = _member(status=Member.Status.ACTIVE)
    assert head.post(P + f"membership/members/{member.pk}/step/approve/").status_code == 403


def test_minors_visible_only_to_head_and_need_guardian_consent(head, clerk, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    minor = _member(
        full_name="Young Person", date_of_birth=(date.today() - timedelta(days=365 * 15)).isoformat()
    )
    assert minor.is_minor and minor.age_band == "under_18"
    assert b"Young Person" not in clerk.get(P + "membership/members/").content
    assert clerk.get(P + f"membership/members/{minor.pk}/").status_code == 404
    assert b"Young Person" in head.get(P + "membership/members/").content
    founder = verified_client(make_staff(superuser=True))
    assert founder.get(P + f"membership/members/{minor.pk}/").status_code == 200
    head.post(P + f"membership/members/{minor.pk}/step/approve/")
    minor.refresh_from_db()
    assert minor.status == "submitted"  # blocked: no guardian consent
    minor.guardian_name, minor.guardian_contact, minor.guardian_consent = "Parent", "+211 911 000 000", True
    minor.save()
    head.post(P + f"membership/members/{minor.pk}/step/approve/")
    minor.refresh_from_db()
    assert minor.status == "approved"


def test_staff_form_requires_guardian_for_minor(clerk) -> None:  # type: ignore[no-untyped-def]
    data = {"full_name": "Kid", "date_of_birth": (date.today() - timedelta(days=365 * 12)).isoformat()}
    resp = clerk.post(P + "membership/members/new/", data)
    assert resp.status_code == 200 and b"guardian" in resp.content
    assert not Member.objects.exists()


def test_branch_coordinator_sees_only_own_branch_and_cannot_decide(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    juba, yei = Branch.objects.get(slug="juba"), Branch.objects.get(slug="yei")
    mine, other = _member(full_name="Juba Person", branch=juba), _member(
        full_name="Yei Person", branch=yei, email="y@example.test"
    )
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))
    page = client.get(P + "membership/members/").content
    assert b"Juba Person" in page and b"Yei Person" not in page
    assert client.get(P + f"membership/members/{other.pk}/").status_code == 404
    assert client.get(P + f"membership/members/{mine.pk}/").status_code == 200
    assert client.post(P + f"membership/members/{mine.pk}/step/review/").status_code == 403
    assert client.get(P + "membership/members/new/").status_code == 403
    assert client.get(P + "membership/members/export.csv").status_code == 403


def test_other_departments_cannot_reach_membership(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    member = _member()
    client = verified_client(make_staff(FINANCE, heads={"finance"}))
    assert client.get(P + "membership/members/").status_code == 403
    assert client.get(P + f"membership/members/{member.pk}/").status_code == 403
    assert client.post(P + f"membership/members/{member.pk}/step/approve/").status_code == 403


def test_attendance_and_engagement_score(clerk) -> None:  # type: ignore[no-untyped-def]
    juba = Branch.objects.get(slug="juba")
    a = _member(status=Member.Status.ACTIVE)
    b = _member(status=Member.Status.ACTIVE, full_name="Peter", email="p@example.test")
    first = Activity.objects.create(name="Sunday", date=timezone.localdate(), branch=juba)
    second = Activity.objects.create(name="Midweek", date=timezone.localdate(), branch=juba)
    clerk.post(P + f"membership/activities/{first.pk}/attendance/", {"present": [a.pk, b.pk]})
    clerk.post(P + f"membership/activities/{second.pk}/attendance/", {"present": [a.pk]})
    a.refresh_from_db()
    b.refresh_from_db()
    assert a.engagement_score == 100 and b.engagement_score == 50
    assert second.attendance.get(member=b).present is False


def test_bulk_email_respects_opt_in_and_excludes_minors(head, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    _member(status="active", comms_opt_in=True, email="yes@example.test")
    _member(status="active", comms_opt_in=False, email="no@example.test")
    _member(
        status="active",
        comms_opt_in=True,
        email="kid@example.test",
        date_of_birth=(date.today() - timedelta(days=365 * 14)).isoformat(),
    )
    message = BulkMessage.objects.create(subject="Prayer week", body="Join us")
    with django_capture_on_commit_callbacks(execute=True):
        assert head.post(P + f"membership/messages/{message.pk}/send/").status_code == 302
    assert [m.to for m in mail.outbox] == [["yes@example.test"]]
    message.refresh_from_db()
    assert message.sent_at and message.recipient_count == 1
    head.post(P + f"membership/messages/{message.pk}/send/")
    assert len(mail.outbox) == 1  # never sent twice


def test_bulk_messages_are_head_only(clerk) -> None:  # type: ignore[no-untyped-def]
    message = BulkMessage.objects.create(subject="x", body="y")
    assert clerk.post(P + f"membership/messages/{message.pk}/send/").status_code == 403
    assert clerk.get(P + f"membership/messages/{message.pk}/whatsapp/").status_code == 403


def test_whatsapp_links(head) -> None:  # type: ignore[no-untyped-def]
    _member(status="active", comms_opt_in=True)
    message = BulkMessage.objects.create(subject="Hi", body="Service at 9", channel="whatsapp")
    page = head.get(P + f"membership/messages/{message.pk}/whatsapp/").content.decode()
    assert "https://wa.me/211900000001?text=Hi" in page


def test_dashboard_and_report_figures(head) -> None:  # type: ignore[no-untyped-def]
    _member(status="active", join_date=timezone.localdate())
    _member(email="b@example.test")
    page = head.get(P + "membership/")
    assert page.status_code == 200
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert kpis["active_members"] == 1 and kpis["pending_approvals"] == 1
    head.post(P + "membership/reports/generate/", {"month": timezone.localdate().strftime("%Y-%m")})
    report = DepartmentReport.objects.get()
    assert {f["code"] for f in report.figures} >= {"active_members", "pending_approvals"}


def test_list_and_detail_views_are_audited(head) -> None:  # type: ignore[no-untyped-def]
    member = _member()
    head.get(P + "membership/members/")
    head.get(P + f"membership/members/{member.pk}/")
    assert AuditLog.objects.filter(action=AuditLog.Action.VIEW, model="member").count() >= 2
