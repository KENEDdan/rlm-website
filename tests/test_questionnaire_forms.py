"""The four public questionnaire forms (docs/membership_policy_questionnaire.md) and their data protection."""

from __future__ import annotations

from datetime import date, timedelta

import pytest
from django.core import mail
from django.db import connection
from django.test import Client
from django.utils import timezone

from accounts.models import User
from core.models import SiteSettings
from core.privacy import erase_person, export_person
from core.tasks import _admin_change_url
from discipleship.models import Registration
from finance.models import Donor, FinanceVolunteer
from giving.models import PartnershipEnquiry
from membership.models import Member

pytestmark = pytest.mark.django_db


def years_ago(n: int) -> str:
    today = date.today()
    return today.replace(year=today.year - n).isoformat()


MEMBER = {
    "full_name": "Grace Akello",
    "gender": "female",
    "date_of_birth": years_ago(30),
    "nationality": "South Sudanese",
    "country": "South Sudan",
    "city": "Juba",
    "phone": "+211 912 345 678",
    "email": "grace@example.test",
    "occupation": "Teacher",
    "born_again": "yes",
    "church_attended": "Juba Revival Church",
    "years_christian": "10 years",
    "testimony": "I met Jesus at a youth camp in 2014.",
    "talents": "Singing, teaching children",
    "declaration": "on",
    "consent": "on",
}
DISCIPLE = {
    "full_name": "Peter Lado",
    "gender": "male",
    "age": "24",
    "nationality": "South Sudanese",
    "country": "South Sudan",
    "city": "Yei",
    "phone": "+211 922 000 000",
    "email": "",
    "born_again": "yes",
    "baptized": "no",
    "attends_church": "yes",
    "journey": "I want to know the Word more deeply.",
    "growth_areas": ["knowledge", "prayer"],
    "consent": "on",
}
PARTNER = {
    "name": "Hope Fellowship Nairobi",
    "country": "Kenya",
    "city": "Nairobi",
    "phone": "+254 700 000 000",
    "email": "partners@hope.example.test",
    "partner_type": "church",
    "areas": ["evangelism", "youth-revival"],
    "partnership_types": ["financial", "prayer"],
    "message": "We would like to support youth conferences.",
    "consent": "on",
}
FIN = {
    "full_name": "Ann Keji",
    "gender": "female",
    "nationality": "South Sudanese",
    "country": "South Sudan",
    "city": "Juba",
    "phone": "+211 933 000 000",
    "email": "ann@example.test",
    "occupation": "Accountant",
    "education_level": "Bachelor's degree",
    "field_of_study": "Accounting",
    "finance_experience": "yes",
    "computer_skills": "Excel, QuickBooks",
    "statement": "Five years in bookkeeping for an NGO.",
    "willing_integrity": "yes",
    "declaration": "on",
    "consent": "on",
}


@pytest.mark.parametrize(
    ("url", "button", "headings"),
    [
        (
            "/membership/register/",
            "REGISTER AS A MEMBER",
            ["A. Personal information", "B. Christian background", "C. Personal statement"],
        ),
        (
            "/discipleship/register/",
            "REGISTER FOR DISCIPLESHIP",
            ["A. Personal information", "B. Spiritual background", "C. Personal statement"],
        ),
        ("/partner/", "BECOME A PARTNER", ["A. Partner information", "B. Partnership interests"]),
        (
            "/get-involved/finance-volunteer/",
            "REGISTER AS A FINANCE VOLUNTEER",
            ["B. Education and professional background"],
        ),
    ],
)
def test_forms_render_with_questionnaire_structure(
    client: Client, url: str, button: str, headings: list[str]
) -> None:
    html = client.get(url).content.decode()
    assert button in html
    for heading in headings:
        assert heading in html
    assert "privacy policy" in html and 'name="website"' in html  # consent text + honeypot


def test_membership_registration_saves_encrypted_and_reaches_the_queue(
    client: Client, django_capture_on_commit_callbacks
) -> None:
    SiteSettings.objects.update(notification_email="office@example.test")
    with django_capture_on_commit_callbacks(execute=True):
        resp = client.post("/membership/register/", MEMBER)
    assert resp.status_code == 302
    member = Member.objects.get()
    assert (
        member.status == "submitted" and member.source == "website" and member.declaration and member.consent
    )
    assert member.age_band == "26_35" and not member.is_minor
    with connection.cursor() as cur:
        cur.execute("SELECT full_name, date_of_birth, testimony, born_again FROM membership_member")
        for raw in cur.fetchone():
            assert raw.startswith("gAAAAA")
    staff_alert = next(m for m in mail.outbox if m.to == ["office@example.test"])
    assert "/membership/members/" in staff_alert.body and "Akello" not in staff_alert.body
    ack = next(m for m in mail.outbox if m.to == ["grace@example.test"])
    assert "youth camp" not in ack.body


def test_declaration_and_consent_are_required(client: Client) -> None:
    for missing in ("declaration", "consent"):
        data = {k: v for k, v in MEMBER.items() if k != missing}
        client.post("/membership/register/", data)
    assert not Member.objects.exists()


def test_minor_member_needs_guardian_and_is_never_on_mailing_lists(client: Client) -> None:
    data = {**MEMBER, "date_of_birth": years_ago(15), "comms_opt_in": "on"}
    client.post("/membership/register/", data)
    assert not Member.objects.exists()
    client.post(
        "/membership/register/",
        {
            **data,
            "guardian_name": "Mama Rose",
            "guardian_contact": "+211 900 000 001",
            "guardian_consent": "on",
        },
    )
    member = Member.objects.get()
    assert member.is_minor and member.guardian_consent and not member.comms_opt_in


def test_discipleship_registration(client: Client) -> None:
    assert client.post("/discipleship/register/", DISCIPLE).status_code == 302
    reg = Registration.objects.get()
    assert reg.growth_areas == ["knowledge", "prayer"] and reg.baptized == "no" and reg.age_band == "18_25"
    client.post("/discipleship/register/", {**DISCIPLE, "age": "14", "phone": "+211 922 000 001"})
    assert Registration.objects.count() == 1  # minor without guardian refused


def test_partnership_registration_feeds_finance_pipeline(client: Client) -> None:
    assert client.post("/partner/", PARTNER).status_code == 302
    enquiry = PartnershipEnquiry.objects.get()
    assert (
        enquiry.areas == ["evangelism", "youth-revival"]
        and enquiry.city == "Nairobi"
        and enquiry.interest == "financial"
    )
    donor = Donor.objects.get(source_enquiry=enquiry)
    assert (
        donor.kind == "church"
        and donor.stage == "prospect"
        and donor.interests == ["evangelism", "youth-revival"]
    )


def test_partner_other_area_needs_description(client: Client) -> None:
    client.post("/partner/", {**PARTNER, "areas": ["other"]})
    assert not PartnershipEnquiry.objects.exists()


def test_finance_volunteer_goes_to_vetting_and_creates_no_account(client: Client) -> None:
    assert client.post("/get-involved/finance-volunteer/", FIN).status_code == 302
    volunteer = FinanceVolunteer.objects.get()
    assert volunteer.status == "submitted" and volunteer.finance_experience == "yes"
    assert not User._base_manager.filter(email="ann@example.test").exists()


def test_honeypot_blocks_all_four(client: Client) -> None:
    for url, data in (
        ("/membership/register/", MEMBER),
        ("/discipleship/register/", DISCIPLE),
        ("/partner/", PARTNER),
        ("/get-involved/finance-volunteer/", FIN),
    ):
        client.post(url, {**data, "website": "http://spam.example"})
    assert not (
        Member.objects.exists()
        or Registration.objects.exists()
        or PartnershipEnquiry.objects.exists()
        or FinanceVolunteer.objects.exists()
    )


def test_staff_alert_links_point_to_the_portal_queues() -> None:
    assert "/membership/members/5/" in _admin_change_url("membership.Member", 5)
    assert "/discipleship/registrations/5/" in _admin_change_url("discipleship.Registration", 5)
    assert "/finance/volunteers/5/" in _admin_change_url("finance.FinanceVolunteer", 5)


def test_unsuccessful_applications_are_purged_after_retention() -> None:
    """Counted from the decision (outcome_at), not the last edit; see tests/test_retention.py for the full rules."""
    from core.tasks import purge_unsuccessful_applications

    Member.objects.create(full_name="Old reject", status="rejected")
    Member.objects.create(full_name="Active", status="active")
    Member.objects.update(outcome_at=timezone.now() - timedelta(days=400))
    result = purge_unsuccessful_applications()
    assert result["deleted"] == 1
    assert list(Member.objects.values_list("status", flat=True)) == ["active"]


def test_data_subject_export_and_erase_cover_new_records(client: Client) -> None:
    client.post("/membership/register/", MEMBER)
    client.post("/partner/", {**PARTNER, "email": "grace@example.test"})
    document = export_person("grace@example.test", actor="test")
    assert "membership.Member" in document and "finance.Donor" in document and "youth camp" in document
    result = erase_person("grace@example.test", actor="test")
    assert result["membership.Member"] == 1
    assert not Member.objects.exists()
    assert Donor.objects.get().name == "[erased on request]"
