"""Part 2: the official Vision and Mission, verbatim, from one source, changed only through approval."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.test import Client

from accounts.roles import MEDIA, TECHNICAL
from core.models import ContentChangeRequest, SiteContent, SiteSettings

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
VM = P + "website/vision-mission/"

# Character for character as received from the ministry (Nov 2026). Do not "fix" anything here.
VISION = (
    "To see a generation of spiritually revived and purpose-driven young people in South Sudan and beyond, "
    "whose lives are rebuilt on biblical foundations and who influence their families, churches, communities "
    "and nations for the glory of God."
)
MISSION = (
    "To proclaim the Gospel of Jesus Christ, facilitate spiritual revival, disciple believers, develop godly "
    "leaders and equip young people to fulfil their God-given purpose through biblical teaching, evangelism, "
    "prayer and practical Christian service."
)


def test_vision_and_mission_are_seeded_exactly() -> None:
    content = SiteContent.load()
    assert content.vision == VISION
    assert content.mission == MISSION
    assert len(VISION) == 239 and len(MISSION) == 247  # guards against invisible edits (spaces, dashes)


def test_used_on_about_home_footer_and_meta_from_one_source(client: Client) -> None:
    home = client.get("/").content.decode()
    about = client.get("/about/").content.decode()
    contact = client.get("/contact/").content.decode()  # any page: the footer
    assert VISION in home and MISSION in home
    assert VISION in about and MISSION in about
    assert VISION in contact  # footer
    description = SiteContent.load().meta_description
    assert description and MISSION.startswith(description.removesuffix("...")) and len(description) <= 158
    for url in ("/", "/about/"):  # pages without their own SEO text
        assert f'name="description" content="{description}"' in client.get(url).content.decode(), url


def test_no_template_or_code_duplicates_the_text() -> None:
    needles = (
        "To see a generation of spiritually revived",
        "To proclaim the Gospel of Jesus Christ, facilitate",
    )
    allowed = {Path("core/migrations/0015_seed_vision_mission.py"), Path("tests/test_vision_mission.py")}
    for folder in ("templates", "core", "programs", "portal", "giving", "static"):
        for path in Path(settings.BASE_DIR, folder).rglob("*"):
            if path.suffix not in {".py", ".html", ".txt", ".js", ".css"}:
                continue
            rel = path.relative_to(settings.BASE_DIR)
            if rel in allowed:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            assert not any(n in text for n in needles), rel


def test_editing_the_page_changes_every_place(client: Client) -> None:
    content = SiteContent.load()
    content.vision = "Changed vision for the test."
    content.save()
    for url in ("/", "/about/", "/contact/"):
        assert "Changed vision for the test." in client.get(url).content.decode()


def test_not_editable_in_the_admin(make_staff: Any, verified_client: Any, admin_prefix: str) -> None:
    client = verified_client(make_staff(TECHNICAL))
    url = f"{admin_prefix}core/sitecontent/1/change/"
    html = client.get(url).content.decode()
    assert 'name="vision"' not in html and 'name="mission"' not in html
    assert VISION in html  # shown read-only, with the link to the approval flow


def test_approval_setting_defaults_on() -> None:
    assert SiteSettings.load().vision_mission_approval_required is True


# ------------------------------------------------------------------ the approval flow
def _draft(client: Client, text: str = "A new vision.", field: str = "vision") -> ContentChangeRequest:
    resp = client.post(VM + "new/", {"field": field, "text": text, "reason": "Board decision"})
    assert resp.status_code == 302, resp.content[:300]
    return ContentChangeRequest.objects.filter(text=text).latest("pk")


def test_draft_preview_approve_publish(make_staff: Any, verified_client: Any, reauth: Any) -> None:
    tech_user = make_staff(TECHNICAL)
    tech = verified_client(tech_user)
    change = _draft(tech)
    assert change.status == "draft" and SiteContent.load().vision == VISION
    preview = tech.get(VM + f"{change.pk}/").content.decode()
    assert "A new vision." in preview and VISION in preview  # proposed + published side by side
    # cannot publish without approval
    tech.post(VM + f"{change.pk}/", {"action": "publish"})
    assert SiteContent.load().vision == VISION
    tech.post(VM + f"{change.pk}/", {"action": "submit"})
    change.refresh_from_db()
    assert change.status == "submitted"
    # the author and other Technical Team members are not approvers
    tech.post(VM + f"{change.pk}/", {"action": "approve"})
    other = verified_client(make_staff(TECHNICAL))
    other.post(VM + f"{change.pk}/", {"action": "approve"})
    change.refresh_from_db()
    assert change.status == "submitted"
    # the Super Admin approves only after re-authenticating
    admin_user = make_staff(superuser=True)
    admin = verified_client(admin_user)
    resp = admin.post(VM + f"{change.pk}/", {"action": "approve"})
    assert "/confirm/" in resp["Location"]
    reauth(admin, admin_user)
    admin.post(VM + f"{change.pk}/", {"action": "approve"})
    change.refresh_from_db()
    assert change.status == "approved" and change.decided_by == admin_user
    tech.post(VM + f"{change.pk}/", {"action": "publish"})
    change.refresh_from_db()
    assert change.status == "published" and change.previous_text == VISION
    assert SiteContent.load().vision == "A new vision."


def test_executive_director_can_approve(make_staff: Any, verified_client: Any, reauth: Any) -> None:
    from accounts.roles import EXECUTIVE
    from finance.models import Approver

    director = make_staff(EXECUTIVE)
    Approver.objects.create(user=director, role="executive_director")
    tech = verified_client(make_staff(TECHNICAL))
    change = _draft(tech, "Director-approved vision.")
    tech.post(VM + f"{change.pk}/", {"action": "submit"})
    client = verified_client(director)
    reauth(client, director)
    client.post(VM + f"{change.pk}/", {"action": "approve"})
    change.refresh_from_db()
    assert change.status == "approved"


def test_reject_needs_a_reason(make_staff: Any, verified_client: Any, reauth: Any) -> None:
    tech = verified_client(make_staff(TECHNICAL))
    change = _draft(tech, "Rejected vision.")
    tech.post(VM + f"{change.pk}/", {"action": "submit"})
    admin_user = make_staff(superuser=True)
    admin = verified_client(admin_user)
    reauth(admin, admin_user)
    admin.post(VM + f"{change.pk}/", {"action": "reject"})
    change.refresh_from_db()
    assert change.status == "submitted"
    admin.post(VM + f"{change.pk}/", {"action": "reject", "note": "Wording not agreed"})
    change.refresh_from_db()
    assert change.status == "rejected" and SiteContent.load().vision == VISION


def test_without_approval_rule_publish_after_preview(make_staff: Any, verified_client: Any) -> None:
    SiteSettings.objects.update(vision_mission_approval_required=False)
    tech = verified_client(make_staff(TECHNICAL))
    change = _draft(tech, "Directly published mission.", field="mission")
    tech.post(VM + f"{change.pk}/", {"action": "publish"})
    assert SiteContent.load().mission == "Directly published mission."
    change.refresh_from_db()
    assert change.status == "published" and change.approval_was_required is False


def test_version_history_and_one_click_rollback(make_staff: Any, verified_client: Any, reauth: Any) -> None:
    SiteSettings.objects.update(vision_mission_approval_required=False)
    tech = verified_client(make_staff(TECHNICAL))
    change = _draft(tech, "Temporary vision.")
    tech.post(VM + f"{change.pk}/", {"action": "publish"})
    SiteSettings.objects.update(vision_mission_approval_required=True)
    original = ContentChangeRequest.objects.filter(field="vision", status="published", text=VISION).get()
    page = tech.get(VM).content.decode()
    assert "Temporary vision." in page and "Restore this version" in page
    # Technical Team rollback waits for approval
    tech.post(VM + f"{original.pk}/rollback/")
    assert SiteContent.load().vision == "Temporary vision."
    pending = ContentChangeRequest.objects.filter(rollback_of=original).latest("pk")
    assert pending.status == "submitted"
    # the Super Admin's rollback is one click (after re-authentication)
    admin_user = make_staff(superuser=True)
    admin = verified_client(admin_user)
    reauth(admin, admin_user)
    admin.post(VM + f"{original.pk}/rollback/")
    assert SiteContent.load().vision == VISION
    pending.refresh_from_db()
    assert pending.status == "superseded"


def test_other_roles_cannot_draft(make_staff: Any, verified_client: Any) -> None:
    media = verified_client(make_staff(MEDIA))
    assert media.get(VM).status_code == 403
    assert media.post(VM + "new/", {"field": "vision", "text": "x"}).status_code == 403
    assert not ContentChangeRequest.objects.filter(text="x").exists()


def test_every_step_is_audit_logged(make_staff: Any, verified_client: Any) -> None:
    from audit.models import AuditLog

    tech = verified_client(make_staff(TECHNICAL))
    change = _draft(tech, "Audited vision.")
    tech.post(VM + f"{change.pk}/", {"action": "submit"})
    steps = list(
        AuditLog.objects.filter(model="contentchangerequest", object_id=str(change.pk)).values_list(
            "extra__step", flat=True
        )
    )
    assert "draft" in steps and "submit" in steps
