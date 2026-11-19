"""Security-relevant paths not covered elsewhere: private files, deletes, HTMX partials, scheduled tasks."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from accounts import tasks
from accounts.roles import BRANCH_COORDINATOR, DISCIPLESHIP, FINANCE, FOUNDER, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from discipleship.models import ClassSession, Cohort, Disciple, Enrollment, Registration, SessionAttendance
from membership.models import Member, MemberDocument

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"


@pytest.fixture
def private_root(tmp_path, settings):  # type: ignore[no-untyped-def]
    settings.PRIVATE_MEDIA_ROOT = tmp_path / "private"
    settings.MEDIA_ROOT = tmp_path / "media"
    return settings.PRIVATE_MEDIA_ROOT


def test_private_file_upload_download_is_scoped_and_audited(private_root, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    member = Member.objects.create(
        full_name="Doc Owner", status="active", branch=Branch.objects.get(slug="juba")
    )
    clerk = verified_client(make_staff(MEMBERSHIP))
    resp = clerk.post(
        P + "membership/documents/new/",
        {
            "member": member.pk,
            "title": "ID copy",
            "file": SimpleUploadedFile("id.pdf", PDF, content_type="application/pdf"),
        },
    )
    assert resp.status_code == 302
    doc = MemberDocument.objects.get()
    stored = private_root / doc.file.name
    assert stored.exists() and not str(doc.file.name).startswith("id")  # random name, outside MEDIA_ROOT
    url = P + f"membership/documents/{doc.pk}/file/file/"
    download = clerk.get(url)
    assert download.status_code == 200 and download["Content-Disposition"].startswith("attachment")
    assert "no-store" in download["Cache-Control"] and b"".join(download.streaming_content).startswith(
        b"%PDF"
    )
    assert AuditLog.objects.filter(action=AuditLog.Action.VIEW, extra__file="file").exists()
    assert (
        clerk.get(P + f"membership/documents/{doc.pk}/file/full_name/").status_code == 404
    )  # only file fields
    assert verified_client(make_staff(FINANCE)).get(url).status_code == 403
    yei = verified_client(make_staff(BRANCH_COORDINATOR, branch=Branch.objects.get(slug="yei")))
    assert yei.get(url).status_code in (403, 404)


def test_upload_rejects_disguised_files(private_root, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    member = Member.objects.create(full_name="X", status="active")
    clerk = verified_client(make_staff(MEMBERSHIP))
    fake = SimpleUploadedFile("evil.pdf", b"<script>alert(1)</script>", content_type="application/pdf")
    resp = clerk.post(P + "membership/documents/new/", {"member": member.pk, "title": "x", "file": fake})
    assert resp.status_code == 200 and not MemberDocument.objects.exists()


def test_delete_needs_head_and_is_audited(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    member = Member.objects.create(full_name="Delete me", status="submitted")
    assert (
        verified_client(make_staff(MEMBERSHIP))
        .post(P + f"membership/members/{member.pk}/delete/")
        .status_code
        == 403
    )
    head = verified_client(make_staff(MEMBERSHIP, heads={"membership"}))
    assert head.get(P + f"membership/members/{member.pk}/delete/").status_code == 200
    head.post(P + f"membership/members/{member.pk}/delete/")
    assert not Member.objects.exists()
    assert AuditLog.objects.filter(action=AuditLog.Action.DELETE, model="member").exists()


def test_htmx_partials(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEMBERSHIP))
    page = client.get(P + "membership/", HTTP_HX_REQUEST="true")
    assert page.status_code == 200 and b"<html" not in page.content and b"kpi" in page.content
    table = client.get(P + "membership/members/?status=active", HTTP_HX_REQUEST="true")
    assert table.status_code == 200 and b"<html" not in table.content
    founder = verified_client(make_staff(FOUNDER, superuser=True))
    assert b"<html" not in founder.get(P + "executive/", HTTP_HX_REQUEST="true").content


def test_list_filters_reject_unknown_values(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    Member.objects.create(full_name="A", status="active")
    client = verified_client(make_staff(MEMBERSHIP))
    assert (
        client.get(P + "membership/members/?status=' OR 1=1--&branch=999999&from=nonsense").status_code == 200
    )


def test_scheduled_account_tasks(make_staff, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    make_staff(FOUNDER, superuser=True, email="f@example.test")
    assert tasks.account_integrity_check() is True
    old = make_staff(email="old@example.test")
    from accounts.models import User

    User.objects.filter(pk=old.pk).update(
        last_login=timezone.now() - timedelta(days=settings.DORMANT_DISABLE_DAYS + 5)
    )
    mail.outbox.clear()
    result = tasks.dormant_accounts()
    assert result["disabled"] == 1 and mail.outbox and "old@example.test" not in mail.outbox[0].body


def test_discipleship_registration_steps_and_class_attendance(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(DISCIPLESHIP))
    reg = Registration.objects.create(
        full_name="R",
        age="30",
        phone="1",
        born_again="yes",
        baptized="yes",
        attends_church="yes",
        journey="x",
        consent=True,
    )
    client.post(P + f"discipleship/registrations/{reg.pk}/step/contacted/")
    reg.refresh_from_db()
    assert reg.status == "contacted"
    cohort = Cohort.objects.create(name="Class A", start_date=timezone.localdate(), status="running")
    assert client.get(P + f"discipleship/registrations/{reg.pk}/enroll/").status_code == 200
    client.post(P + f"discipleship/registrations/{reg.pk}/enroll/", {"cohort": cohort.pk})
    reg.refresh_from_db()
    disciple = reg.disciple
    assert reg.status == "enrolled" and Enrollment.objects.filter(cohort=cohort, disciple=disciple).exists()
    other = Disciple.objects.create(full_name="Absent one")
    Enrollment.objects.create(cohort=cohort, disciple=other)
    session = ClassSession.objects.create(cohort=cohort, topic="Prayer")
    assert client.get(P + f"discipleship/sessions/{session.pk}/attendance/").status_code == 200
    client.post(P + f"discipleship/sessions/{session.pk}/attendance/", {"present": [disciple.pk]})
    assert SessionAttendance.objects.get(session=session, disciple=disciple).present
    assert not SessionAttendance.objects.get(session=session, disciple=other).present
    declined = Registration.objects.create(
        full_name="D",
        age="30",
        phone="1",
        born_again="yes",
        baptized="yes",
        attends_church="yes",
        journey="x",
        consent=True,
    )
    client.post(P + f"discipleship/registrations/{declined.pk}/step/declined/")
    client.post(P + f"discipleship/registrations/{declined.pk}/step/contacted/")
    declined.refresh_from_db()
    assert declined.status == "declined"
