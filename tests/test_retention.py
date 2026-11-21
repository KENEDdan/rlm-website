"""Decision 8: application outcomes, conversion with a reference only, retention purge, dry run, legal hold,
early deletion, minors, anonymous statistics, monthly report, notices."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

import pytest
from django.conf import settings
from django.core import mail
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import Client
from django.utils import timezone

from accounts.roles import DISCIPLESHIP, FINANCE, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch
from core import retention
from core.models import ApplicationStat, SiteSettings
from core.tasks import purge_unsuccessful_applications, report_applications_nearing_purge
from discipleship.models import Disciple, Registration
from discipleship.services import enroll_registration
from finance.models import Donor, FinanceVolunteer
from giving.models import PartnershipEnquiry
from membership.models import Member, MemberDocument

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
OLD = timezone.now() - timedelta(days=400)


def _reject_member(**kw) -> Member:  # type: ignore[no-untyped-def]
    member = Member.objects.create(
        full_name=kw.pop("full_name", "Rejected Person"),
        phone="+211 900 000 001",
        email="reject@example.test",
        testimony="private testimony",
        status="submitted",
        **kw,
    )
    member.status = "rejected"
    member.save()
    return member


def _dob(years: int) -> str:
    today = timezone.localdate()
    return today.replace(year=today.year - years).isoformat()


def _age(obj, when=OLD) -> None:  # type: ignore[no-untyped-def]
    type(obj).objects.filter(pk=obj.pk).update(outcome_at=when)


def test_outcome_follows_status_and_starts_the_clock() -> None:
    member = Member.objects.create(full_name="A", status="submitted")
    assert member.outcome == "pending" and member.outcome_at is None
    member.status = "rejected"
    member.save()
    assert member.outcome == "unsuccessful" and member.outcome_at is not None
    member.status = "approved"
    member.save()
    assert member.outcome == "successful" and member.record_reference == "Member register"
    assert ApplicationStat.objects.get(kind="membership", outcome="successful").count == 1


def test_purge_deletes_only_past_deadline_and_keeps_anonymous_stats(django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    branch = Branch.objects.get(slug="juba")
    old = _reject_member(branch=branch)
    doc = MemberDocument.objects.create(member=old, title="ID", file=ContentFile(b"secret", name="id.pdf"))
    storage, file_name = doc.file.storage, doc.file.name
    _age(old)
    recent = _reject_member(full_name="Recent")
    active = Member.objects.create(full_name="Active", status="active")
    vol = FinanceVolunteer.objects.create(
        full_name="V",
        phone="1",
        email="v@example.test",
        education_level="x",
        finance_experience="no",
        status="declined",
    )
    _age(vol)
    with django_capture_on_commit_callbacks(execute=True):
        result = purge_unsuccessful_applications()
    assert (
        result["deleted"] == 2
        and result["due"]["membership"] == 1
        and result["due"]["finance_volunteer"] == 1
    )
    assert set(Member.objects.values_list("pk", flat=True)) == {recent.pk, active.pk}
    assert not FinanceVolunteer.objects.exists() and not MemberDocument.objects.exists()
    assert not storage.exists(file_name)  # uploaded files go too
    stat = ApplicationStat.objects.get(kind="membership", outcome="unsuccessful")
    assert stat.count == 1 and stat.branch == branch
    # anonymization completeness: no identifying value survives anywhere in the statistics or the audit entry
    stats_text = str(list(ApplicationStat.objects.values()))
    log = AuditLog.objects.filter(action=AuditLog.Action.PURGE).latest("timestamp")
    for secret in ("Rejected Person", "reject@example.test", "+211 900 000 001", "private testimony"):
        assert secret not in stats_text and secret not in str(log.extra)


def test_every_run_is_audit_logged_even_when_nothing_is_due() -> None:
    purge_unsuccessful_applications()
    log = AuditLog.objects.get(action=AuditLog.Action.PURGE)
    assert log.extra["deleted"] == 0 and log.actor_email == "system:application-retention"


def test_dry_run_deletes_nothing() -> None:
    old = _reject_member()
    _age(old)
    out = StringIO()
    call_command("purge_applications", "--dry-run", stdout=out)
    assert f"Membership application #{old.pk}" in out.getvalue()
    assert Member.objects.filter(pk=old.pk).exists() and not AuditLog.objects.filter(action="purge").exists()


def test_legal_hold_pauses_deletion() -> None:
    old = _reject_member()
    Member.objects.filter(pk=old.pk).update(outcome_at=OLD, legal_hold=True, legal_hold_reason="Court case")
    purge_unsuccessful_applications()
    assert Member.objects.filter(pk=old.pk).exists()


def test_minors_are_kept_for_a_shorter_period() -> None:
    minor = _reject_member(full_name="Young", date_of_birth=_dob(15))
    assert minor.is_minor
    _age(minor, timezone.now() - timedelta(days=100))
    adult = _reject_member(full_name="Adult")
    _age(adult, timezone.now() - timedelta(days=100))
    purge_unsuccessful_applications()
    assert not Member.objects.filter(pk=minor.pk).exists() and Member.objects.filter(pk=adult.pk).exists()
    site = SiteSettings.load()
    site.retention_unsuccessful_days = 0  # "keep" switches deletion off for everyone, minors included
    site.save()
    young = _reject_member(full_name="Young 2", date_of_birth=_dob(15))
    _age(young)
    purge_unsuccessful_applications()
    assert Member.objects.filter(pk=young.pk).exists()


def test_minor_applications_visible_to_head_only(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    minor = Member.objects.create(full_name="Young", date_of_birth=_dob(15), status="submitted")
    member = verified_client(make_staff(MEMBERSHIP))
    head = verified_client(make_staff(MEMBERSHIP, heads={"membership"}))
    assert member.get(P + f"membership/members/{minor.pk}/").status_code == 404
    page = head.get(P + f"membership/members/{minor.pk}/")
    assert page.status_code == 200 and b"Retention deadline" in page.content


def test_discipleship_conversion_keeps_only_a_reference(rf, make_staff) -> None:  # type: ignore[no-untyped-def]
    reg = Registration.objects.create(
        full_name="Peter Lado",
        phone="+211 922 000 000",
        email="p@example.test",
        born_again="yes",
        baptized="no",
        attends_church="yes",
        journey="My journey",
        age="24",
        consent=True,
    )
    request = rf.post("/")
    request.user = make_staff(DISCIPLESHIP, heads={"discipleship"})
    disciple = enroll_registration(request, reg)
    reg.refresh_from_db()
    assert disciple.full_name == "Peter Lado" and Disciple.objects.get(registration=reg) == disciple
    assert reg.outcome == "successful" and reg.record_reference == f"Disciple #{disciple.pk}"
    for field in ("full_name", "phone", "email", "journey", "age", "born_again"):
        assert getattr(reg, field) in ("", None), field
    assert ApplicationStat.objects.get(kind="discipleship", outcome="successful").count == 1


def test_partnership_outcomes(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    enquiry = PartnershipEnquiry.objects.create(
        partner_type="church", name="Hope Church", email="h@example.test", country="Kenya", message="Hello"
    )
    head = verified_client(make_staff(FINANCE, heads={"finance"}))
    member = verified_client(make_staff(FINANCE))
    assert member.post(P + f"finance/partner-registrations/{enquiry.pk}/step/successful/").status_code == 403
    head.post(P + f"finance/partner-registrations/{enquiry.pk}/step/successful/")
    enquiry.refresh_from_db()
    donor = Donor.objects.get(source_enquiry=enquiry)
    assert donor.name == "Hope Church" and enquiry.outcome == "successful"
    assert enquiry.name == "" and enquiry.email == "" and enquiry.record_reference == f"Partner #{donor.pk}"
    other = PartnershipEnquiry.objects.create(
        partner_type="church", name="Gone", email="g@example.test", country="Kenya"
    )
    gone = Donor.objects.create(name="Gone", source_enquiry=other)
    head.post(P + f"finance/partner-registrations/{other.pk}/step/unsuccessful/")
    other.refresh_from_db()
    assert other.outcome == "unsuccessful"
    _age(other)
    purge_unsuccessful_applications()
    assert not PartnershipEnquiry.objects.filter(pk=other.pk).exists()
    assert not Donor.objects.filter(pk=gone.pk).exists()  # the prospect created from it goes too


def test_super_admin_screen_preview_hold_and_early_deletion(make_staff, verified_client, reauth) -> None:  # type: ignore[no-untyped-def]
    old = _reject_member()
    _age(old)
    pending = Member.objects.create(full_name="Asked to be forgotten", status="submitted")
    head = verified_client(make_staff(MEMBERSHIP, heads={"membership"}))
    assert head.get(P + "retention/").status_code == 403
    founder_user = make_staff(superuser=True)
    founder = verified_client(founder_user)
    page = founder.get(P + "retention/")
    assert (
        f"Membership application #{old.pk}".encode() in page.content
        and Member.objects.filter(pk=old.pk).exists()
    )
    founder.post(
        P + "retention/", {"action": "hold", "kind": "membership", "pk": old.pk, "reason": "Dispute open"}
    )
    assert Member.objects.get(pk=old.pk).legal_hold
    # early deletion needs re-authentication, a reason, and no legal hold
    resp = founder.post(
        P + "retention/", {"action": "erase", "kind": "membership", "pk": pending.pk, "reason": "Email 3 May"}
    )
    assert "/accounts/confirm/" in resp["Location"] and Member.objects.filter(pk=pending.pk).exists()
    reauth(founder, founder_user)
    founder.post(
        P + "retention/", {"action": "erase", "kind": "membership", "pk": old.pk, "reason": "Email 3 May"}
    )
    assert Member.objects.filter(pk=old.pk).exists()  # on hold
    founder.post(
        P + "retention/", {"action": "erase", "kind": "membership", "pk": pending.pk, "reason": "Email 3 May"}
    )
    assert not Member.objects.filter(pk=pending.pk).exists()
    assert any("early_deletion" in log.extra for log in AuditLog.objects.filter(action=AuditLog.Action.PURGE))
    assert ApplicationStat.objects.get(kind="membership", outcome="pending").count == 1


def test_monthly_report_to_department_heads_without_personal_data(make_staff) -> None:  # type: ignore[no-untyped-def]
    make_staff(MEMBERSHIP, heads={"membership"}, email="head@example.test")
    soon = _reject_member(full_name="Nearly Gone")
    _age(soon, timezone.now() - timedelta(days=350))  # deleted in 15 days
    mail.outbox.clear()
    assert report_applications_nearing_purge() == 1
    message = next(m for m in mail.outbox if m.to == ["head@example.test"])
    assert "Membership application: 1 to be deleted" in message.body
    assert "Nearly Gone" not in message.body and "reject@example.test" not in message.body


def test_forms_and_privacy_policy_tell_applicants(client: Client) -> None:
    for url in ("/membership/register/", "/partner/"):
        assert b"we delete it 365 days after the decision" in client.get(url).content, url
    page = client.get("/privacy/").content.decode()
    assert "applications that are not successful" in page and "under 18" in page
    assert "the application itself keeps only a reference" in page


def test_deadline_text() -> None:
    old = _reject_member()
    old.refresh_from_db()
    assert retention.deadline_text(old).startswith("Deleted automatically on")
    Member.objects.filter(pk=old.pk).update(legal_hold=True, legal_hold_reason="Court")
    old.refresh_from_db()
    assert retention.deadline_text(old).startswith("On legal hold")


def test_lifting_a_legal_hold_needs_reauthentication(make_staff, verified_client, reauth) -> None:  # type: ignore[no-untyped-def]
    held = _reject_member()
    Member.objects.filter(pk=held.pk).update(legal_hold=True, legal_hold_reason="Court case")
    founder_user = make_staff(superuser=True)
    founder = verified_client(founder_user)
    resp = founder.post(P + "retention/", {"action": "release", "kind": "membership", "pk": held.pk})
    assert "/accounts/confirm/" in resp["Location"] and Member.objects.get(pk=held.pk).legal_hold
    reauth(founder, founder_user)
    founder.post(P + "retention/", {"action": "release", "kind": "membership", "pk": held.pk})
    assert not Member.objects.get(pk=held.pk).legal_hold
