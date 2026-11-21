"""Part 4: the Technical Team (Website Administration) and separation of duties; protected bank details;
finance enquiries routed only to Finance; every website change versioned with rollback."""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core import mail
from django.test import Client

from accounts.roles import (
    BRANCH_COORDINATOR,
    DEPARTMENT_GROUPS,
    EXECUTIVE,
    FINANCE,
    MEMBERSHIP,
    TECHNICAL,
    TECHNICAL_FORBIDDEN_APPS,
    TECHNICAL_FORBIDDEN_MODELS,
)
from branches.models import Branch
from contact.models import ContactMessage
from core.models import ContentVersion, SocialLink
from giving.models import BankDetailChange, BankDetailsLocked, GivingSettings

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
BANK = P + "finance/bank-details/"
NEW_NUMBER = "0011223344556677"


# ------------------------------------------------------------------ what the role can and cannot touch
def test_technical_team_group_has_website_permissions_only() -> None:
    group = Group.objects.get(name=TECHNICAL)
    perms = set(group.permissions.values_list("content_type__app_label", "content_type__model"))
    assert (
        ("core", "sitecontent") in perms
        and ("programs", "activity") in perms
        and ("core", "heroslide") in perms
    )
    assert not {app for app, _ in perms} & TECHNICAL_FORBIDDEN_APPS
    assert not perms & TECHNICAL_FORBIDDEN_MODELS
    assert ("giving", "givingsettings") not in perms and ("giving", "bankdetailchange") not in perms


@pytest.mark.parametrize(
    "path",
    ["core/sitecontent/", "core/heroslide/", "programs/activity/", "programs/activitycategory/", "core/page/",
     "core/sociallink/", "core/pagetext/", "leadership/leader/", "branches/branch/", "media_library/album/"],
)  # fmt: skip
def test_technical_team_manages_website_content(
    make_staff: Any, verified_client: Any, admin_prefix: str, path: str
) -> None:
    assert verified_client(make_staff(TECHNICAL)).get(admin_prefix + path).status_code in (200, 302)


@pytest.mark.parametrize(
    "path",
    ["giving/givingsettings/", "giving/donation/", "giving/partnershipenquiry/", "prayer/prayerrequest/",
     "registrations/volunteerapplication/", "contact/contactmessage/", "accounts/user/", "auth/group/",
     "core/sitesettings/", "core/uploadlimit/", "audit/auditlog/", "newsletter/subscriber/"],
)  # fmt: skip
def test_technical_team_cannot_reach_sensitive_admin(
    make_staff: Any, verified_client: Any, admin_prefix: str, path: str
) -> None:
    assert verified_client(make_staff(TECHNICAL)).get(admin_prefix + path).status_code in (403, 404)


@pytest.mark.parametrize(
    "path",
    ["finance/", "finance/ledger/", "finance/donors/", "membership/", "membership/members/", "discipleship/",
     "missions/", "executive/", "executive/finance/", "approvals/", "accounts/", "retention/",
     "finance/bank-details/", "finance/enquiries/"],
)  # fmt: skip
def test_technical_team_cannot_reach_portal_records(make_staff: Any, verified_client: Any, path: str) -> None:
    resp = verified_client(make_staff(TECHNICAL)).get(P + path)
    assert resp.status_code in (403, 404), path


def test_technical_team_lands_on_the_website_dashboard(make_staff: Any, verified_client: Any) -> None:
    client = verified_client(make_staff(TECHNICAL))
    resp = client.get(P)
    assert resp.status_code == 302 and resp["Location"].endswith("/website/")
    page = client.get(P + "website/")
    html = page.content.decode()
    assert page.status_code == 200
    for section in ("Drafts awaiting publish", "Pages needing updates", "Recent changes", "Broken links",
                    "Site health", "Last backup", "Upload storage"):  # fmt: skip
        assert section in html
    nav = client.get(P + "website/hero/").content.decode()
    assert "Website dashboard" in nav and "Bank details" not in nav and "Staff accounts" not in nav


@pytest.mark.parametrize("role", [MEMBERSHIP, FINANCE, EXECUTIVE, BRANCH_COORDINATOR])
def test_other_roles_cannot_open_the_website_dashboard(
    make_staff: Any, verified_client: Any, role: str
) -> None:
    kw = {"branch": Branch.objects.get(slug="juba")} if role == BRANCH_COORDINATOR else {}
    assert verified_client(make_staff(role, **kw)).get(P + "website/").status_code == 403


def test_only_the_super_admin_assigns_the_technical_team_role(
    make_staff: Any, verified_client: Any, reauth: Any
) -> None:
    target = make_staff()
    url = P + f"accounts/{target.pk}/roles/"
    other = verified_client(make_staff(FINANCE, heads={"finance"}))
    assert other.post(url, {"technical": "on"}).status_code == 403
    assert not target.groups.filter(name=TECHNICAL).exists()
    admin_user = make_staff(superuser=True)
    client = verified_client(admin_user)
    reauth(client, admin_user)
    assert "Technical Team (Website Administration)" in client.get(url).content.decode()
    assert client.post(url, {"technical": "on"}).status_code == 302
    assert target.groups.filter(name=TECHNICAL).exists()


def test_dashboard_flags_broken_links_and_missing_images(make_staff: Any, verified_client: Any) -> None:
    from core.models import HeroSlide

    HeroSlide.objects.create(title="Broken", button_text="Go", button_link="/no-such-page/")
    HeroSlide.objects.create(title="Missing image", image="hero/2026/11/missing.jpg")
    html = verified_client(make_staff(TECHNICAL)).get(P + "website/").content.decode()
    assert "No page on this website has this address." in html and "The file is missing." in html


def test_backup_status_shown(make_staff: Any, verified_client: Any) -> None:
    from django.utils import timezone

    from core.models import BackupRun

    client = verified_client(make_staff(TECHNICAL))
    assert "No successful backup recorded" in client.get(P + "website/").content.decode()
    BackupRun.objects.create(finished_at=timezone.now(), ok=True, detail="ok")
    assert "No successful backup recorded" not in client.get(P + "website/").content.decode()


# ------------------------------------------------------------------ versions and rollback
def test_every_change_is_versioned_and_can_be_rolled_back(
    make_staff: Any, verified_client: Any, admin_prefix: str
) -> None:
    from audit.models import AuditLog

    client = verified_client(make_staff(TECHNICAL))
    link = SocialLink.objects.create(platform="facebook", url="https://facebook.com/old")
    url = f"{admin_prefix}core/sociallink/{link.pk}/change/"
    data = {
        "platform": "facebook",
        "label": "",
        "url": "https://facebook.com/new",
        "order": 0,
        "is_published": "on",
    }
    assert client.post(url, data).status_code == 302
    versions = ContentVersion.objects.filter(object_id=str(link.pk), content_type__model="sociallink")
    assert versions.count() == 1 and versions.first().data["url"] == "https://facebook.com/new"
    assert AuditLog.objects.filter(model="sociallink", action="change").exists()
    # rolling back to the first recorded state needs a version of the old state: edit again, then restore #1
    data["url"] = "https://facebook.com/newer"
    client.post(url, data)
    first = versions.order_by("created_at", "pk").first()
    assert client.post(P + f"website/versions/{first.pk}/restore/").status_code == 302
    link.refresh_from_db()
    assert link.url == "https://facebook.com/new"
    assert ContentVersion.objects.filter(action="rollback", object_id=str(link.pk)).exists()


def test_versions_are_append_only() -> None:
    link = SocialLink.objects.create(platform="x", url="https://x.com/a")
    from core.versioning import record

    version = record(link, "change")
    with pytest.raises(PermissionError):
        version.delete()
    version.note = "tamper"
    with pytest.raises(PermissionError):
        version.save()


def test_deleted_content_can_be_restored(make_staff: Any, verified_client: Any, admin_prefix: str) -> None:
    client = verified_client(make_staff(TECHNICAL))
    link = SocialLink.objects.create(platform="youtube", url="https://youtube.com/@rlm")
    client.post(f"{admin_prefix}core/sociallink/{link.pk}/delete/", {"post": "yes"})
    assert not SocialLink.objects.filter(pk=link.pk).exists()
    deleted = ContentVersion.objects.get(action="delete", object_id=str(link.pk))
    client.post(P + f"website/versions/{deleted.pk}/restore/")
    assert SocialLink.objects.get(pk=link.pk).url == "https://youtube.com/@rlm"


# ------------------------------------------------------------------ bank details (fraud prevention)
@pytest.fixture
def finance_head(make_staff: Any) -> Any:
    return make_staff(FINANCE, heads={"finance"})


def _propose(client: Client, reason: str = "New account") -> Any:
    data = {
        "bank_transfer_enabled": "on", "account_name": "RLM Main", "bank_name": "Example Bank",
        "account_number": NEW_NUMBER, "swift_code": "EXAMPLE1", "branch_name": "Juba", "currency": "USD",
        "transfer_instructions": "", "mobile_money_instructions": "", "reason": reason,
    }  # fmt: skip
    return client.post(BANK + "change/", data)


@pytest.mark.parametrize(
    "role",
    [TECHNICAL, *[g for g in DEPARTMENT_GROUPS if g != FINANCE], EXECUTIVE, BRANCH_COORDINATOR, FINANCE],
)
def test_no_other_role_can_read_or_edit_bank_details(
    make_staff: Any, verified_client: Any, role: str
) -> None:
    """Technical Team, every department, Executive Leadership, coordinators and ordinary Finance members."""
    kw = {"branch": Branch.objects.get(slug="juba")} if role == BRANCH_COORDINATOR else {}
    client = verified_client(make_staff(role, **kw))
    assert client.get(BANK).status_code == 403
    assert client.get(BANK + "change/").status_code == 403
    assert _propose(client).status_code == 403
    assert not BankDetailChange.objects.exists()


def test_bank_change_needs_reauth_second_person_and_alerts(
    finance_head: Any, make_staff: Any, verified_client: Any, reauth: Any, client: Client
) -> None:
    head = verified_client(finance_head)
    resp = head.get(BANK + "change/")
    assert resp.status_code == 302 and "/confirm/" in resp["Location"]  # password + 2FA first
    reauth(head, finance_head)
    mail.outbox.clear()
    assert _propose(head).status_code == 302
    change = BankDetailChange.objects.get()
    assert change.status == "pending" and GivingSettings.load().account_number == ""
    assert b"Bank details coming soon" in client.get("/give/").content  # nothing live yet
    alert = mail.outbox[-1]
    assert NEW_NUMBER not in alert.body and "****6677" in alert.body
    assert finance_head.email in alert.to
    # the proposer cannot confirm their own change
    head.post(BANK + f"{change.pk}/", {"action": "confirm"})
    change.refresh_from_db()
    assert change.status == "pending"
    # a second authorised person confirms after re-authenticating
    founder = make_staff(superuser=True)
    second = verified_client(founder)
    resp = second.post(BANK + f"{change.pk}/", {"action": "confirm"})
    assert "/confirm/" in resp["Location"]
    reauth(second, founder)
    second.post(BANK + f"{change.pk}/", {"action": "confirm"})
    change.refresh_from_db()
    gs = GivingSettings.load()
    assert change.status == "confirmed" and gs.account_number == NEW_NUMBER
    assert gs.bank_details_verified_by == founder and change.previous  # history keeps what was replaced
    assert NEW_NUMBER not in mail.outbox[-1].body
    give = client.get("/give/").content.decode()
    assert NEW_NUMBER in give and "Last verified" in give


def test_bank_details_cannot_be_changed_outside_the_flow(
    finance_head: Any, verified_client: Any, admin_prefix: str
) -> None:
    gs = GivingSettings.load()
    gs.account_number = "999"
    with pytest.raises(BankDetailsLocked):
        gs.save()
    html = (
        verified_client(finance_head).get(f"{admin_prefix}giving/givingsettings/1/change/").content.decode()
    )
    assert 'name="account_number"' not in html and 'name="bank_name"' not in html


def test_only_one_pending_change_and_history_kept(
    finance_head: Any, verified_client: Any, reauth: Any
) -> None:
    head = verified_client(finance_head)
    reauth(head, finance_head)
    _propose(head)
    _propose(head, reason="Second")
    assert BankDetailChange.objects.count() == 1
    change = BankDetailChange.objects.get()
    head.post(BANK + f"{change.pk}/", {"action": "cancel"})
    change.refresh_from_db()
    assert change.status == "cancelled"
    with pytest.raises(PermissionError):
        change.delete()


def test_executive_director_can_confirm(
    finance_head: Any, make_staff: Any, verified_client: Any, reauth: Any
) -> None:
    from finance.models import Approver

    head = verified_client(finance_head)
    reauth(head, finance_head)
    _propose(head)
    director = make_staff(EXECUTIVE)
    Approver.objects.create(user=director, role="executive_director")
    client = verified_client(director)
    assert client.get(BANK).status_code == 200
    reauth(client, director)
    client.post(BANK + f"{BankDetailChange.objects.get().pk}/", {"action": "confirm"})
    assert GivingSettings.load().account_number == NEW_NUMBER


# ------------------------------------------------------------------ enquiries routed to Finance only
def _contact(client: Client, category: str) -> ContactMessage:
    data = {
        "name": "Ama", "email": "ama@example.test", "phone": "", "category": category, "topic": "general",
        "subject": "Question", "message": "Hello", "consent": "on", "website": "",
    }  # fmt: skip
    resp = client.post("/contact/", data)
    assert resp.status_code in (200, 302), resp.content[:300]
    return ContactMessage.objects.latest("pk")


def test_contact_form_has_subject_selector(client: Client) -> None:
    html = client.get("/contact/").content.decode()
    assert "Giving and finance" in html and "Partnership" in html and 'name="category"' in html


def test_finance_enquiries_go_only_to_the_finance_queue(
    finance_head: Any, make_staff: Any, verified_client: Any, admin_prefix: str, client: Client
) -> None:
    from core.models import SiteSettings
    from core.tasks import alert_recipients

    SiteSettings.objects.update(notification_email="office@example.test")
    giving = _contact(client, "giving")
    general = _contact(client, "general")
    assert giving.is_finance_queue and not general.is_finance_queue
    assert alert_recipients(ContactMessage, giving.pk) == [finance_head.email]
    assert alert_recipients(ContactMessage, general.pk) == ["office@example.test"]
    membership = verified_client(make_staff(MEMBERSHIP))
    assert membership.get(f"{admin_prefix}contact/contactmessage/{giving.pk}/change/").status_code in (
        302,
        404,
    )
    assert membership.get(f"{admin_prefix}contact/contactmessage/{general.pk}/change/").status_code == 200
    finance = verified_client(finance_head)
    listing = finance.get(P + "finance/enquiries/").content.decode()
    assert f"#{giving.pk}" in listing and f"#{general.pk}" not in listing
    assert finance.get(P + f"finance/enquiries/{general.pk}/").status_code == 404


def test_partnership_and_pledge_alerts_go_to_finance_only(finance_head: Any) -> None:
    from decimal import Decimal

    from core.models import SiteSettings
    from core.tasks import alert_recipients
    from giving.models import Donation, PartnershipEnquiry

    SiteSettings.objects.update(notification_email="office@example.test")
    pledge = Donation.objects.create(
        amount=Decimal("10"), currency="USD", provider="manual_bank", status="pledged"
    )
    assert alert_recipients(Donation, pledge.pk) == [finance_head.email]
    assert PartnershipEnquiry.is_finance_queue
