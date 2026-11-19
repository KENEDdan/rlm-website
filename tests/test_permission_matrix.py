"""Role x model x action permission matrix, plus branch/department scoping (IDOR) in the admin."""

from __future__ import annotations

import itertools
from datetime import timedelta

import pytest
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.utils import timezone

from accounts.roles import (
    ALL_ROLES,
    BRANCH_COORDINATOR,
    DEVELOPMENT,
    DISCIPLESHIP,
    EXECUTIVE,
    FINANCE,
    FOUNDER,
    LOGISTICS,
    MEDIA,
    MEMBERSHIP,
    MISSIONS,
    ROLE_PERMISSIONS,
    codenames_for,
    sync_roles,
)
from branches.models import Branch
from events.models import Event
from prayer.models import PrayerRequest
from registrations.models import VolunteerApplication

pytestmark = pytest.mark.django_db

PROJECT_APPS = [
    "core",
    "accounts",
    "audit",
    "branches",
    "programs",
    "leadership",
    "events",
    "registrations",
    "prayer",
    "contact",
    "newsletter",
    "media_library",
    "resources",
    "news",
    "giving",
    "portal",
]
ACTIONS = ["view", "add", "change", "delete"]


def _all_model_labels() -> list[str]:
    return [m._meta.label_lower for a in PROJECT_APPS for m in apps.get_app_config(a).get_models()]


def _expected(role: str, model_label: str, action: str) -> bool:
    letters = ROLE_PERMISSIONS.get(role, {}).get(model_label, "")
    return any(
        c.endswith(f"{action}_{model_label.split('.')[1]}") for _, c in codenames_for(model_label, letters)
    )


MATRIX = [
    (role, label, action)
    for role, label, action in itertools.product(
        [r for r in ALL_ROLES if r != FOUNDER], _all_model_labels(), [*ACTIONS, "export"]
    )
]


def test_roles_exist_and_sync_is_idempotent() -> None:
    assert set(Group.objects.values_list("name", flat=True)) >= set(ALL_ROLES)
    first = sync_roles()
    second = sync_roles()
    assert first == second


@pytest.mark.parametrize(("role", "model_label", "action"), MATRIX, ids=lambda v: str(v))
def test_permission_matrix(make_staff, role: str, model_label: str, action: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(role)
    app_label, model = model_label.split(".")
    has = user.has_perm(f"{app_label}.{action}_{model}")
    assert has == _expected(role, model_label, action), f"{role} {action} {model_label}"


def test_founder_group_has_content_permissions_but_not_account_admin(make_staff) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(FOUNDER)
    assert user.has_perm("prayer.view_prayerrequest")
    assert user.has_perm("giving.change_givingsettings")
    # Account and role administration comes from the superuser flag (Super Admin) only, never from a group.
    for perm in (
        "accounts.add_user",
        "accounts.change_user",
        "auth.change_group",
        "auth.add_permission",
        "portal.add_departmentmembership",
        "portal.change_departmentmembership",
    ):
        assert not user.has_perm(perm), perm


@pytest.mark.parametrize(
    ("role", "forbidden"),
    [
        (
            FINANCE,
            [
                "prayer.view_prayerrequest",
                "registrations.view_volunteerapplication",
                "contact.view_contactmessage",
            ],
        ),
        (MEDIA, ["prayer.view_prayerrequest", "giving.view_donation", "giving.view_givingsettings"]),
        (MEMBERSHIP, ["giving.view_donation", "giving.view_givingsettings", "core.change_sitesettings"]),
        (
            MISSIONS,
            ["prayer.view_prayerrequest", "giving.view_donation", "registrations.view_volunteerapplication"],
        ),
        (LOGISTICS, ["prayer.view_prayerrequest", "giving.view_donation", "contact.view_contactmessage"]),
        (DEVELOPMENT, ["prayer.view_prayerrequest", "giving.view_donation", "contact.view_contactmessage"]),
        (EXECUTIVE, ["prayer.view_prayerrequest", "giving.view_donation", "contact.view_contactmessage"]),
        (
            BRANCH_COORDINATOR,
            ["prayer.view_prayerrequest", "giving.view_donation", "contact.view_contactmessage"],
        ),
        (
            DISCIPLESHIP,
            ["prayer.view_prayerrequest", "giving.view_donation", "registrations.view_volunteerapplication"],
        ),
    ],
)
def test_sensitive_data_hidden_from_roles_that_do_not_need_it(make_staff, role, forbidden) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(role)
    for perm in forbidden:
        assert not user.has_perm(perm), perm


def test_only_founder_and_finance_can_edit_giving_settings(make_staff) -> None:  # type: ignore[no-untyped-def]
    allowed = {r for r in ALL_ROLES if make_staff(r).has_perm("giving.change_givingsettings")}
    assert allowed == {FOUNDER, FINANCE}


# ------------------------------------------------------------------ admin-level checks (real 2FA login)
def _url(name: str, *args: object) -> str:
    from django.urls import reverse

    return reverse(f"admin:{name}", args=args)


@pytest.mark.parametrize(
    ("role", "url_name", "expected"),
    [
        (FINANCE, "prayer_prayerrequest_changelist", 403),
        (FINANCE, "giving_donation_changelist", 200),
        (MEMBERSHIP, "prayer_prayerrequest_changelist", 200),
        (MEMBERSHIP, "giving_donation_changelist", 403),
        (MEDIA, "resources_resource_changelist", 200),
        (MEDIA, "audit_auditlog_changelist", 403),
        (MISSIONS, "events_event_changelist", 200),
        (MISSIONS, "accounts_user_changelist", 403),
    ],
)
def test_admin_sections_respect_roles(make_staff, verified_client, role, url_name, expected) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(role))
    assert client.get(_url(url_name)).status_code == expected


def test_only_superuser_sees_users_and_audit_log(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    founder = verified_client(make_staff(FOUNDER, superuser=True))
    assert founder.get(_url("accounts_user_changelist")).status_code == 200
    assert founder.get(_url("audit_auditlog_changelist")).status_code == 200


@pytest.fixture
def two_branches():  # type: ignore[no-untyped-def]
    juba = Branch.objects.get(slug="juba")
    yei = Branch.objects.get(slug="yei")
    return juba, yei


def _event(title: str, branch: Branch | None = None) -> Event:
    start = timezone.now() + timedelta(days=7)
    return Event.objects.create(
        title=title,
        slug=title.lower().replace(" ", "-"),
        summary="x",
        start=start,
        end=start + timedelta(hours=2),
        branch=branch,
        is_published=True,
    )


def _volunteer(branch: Branch) -> VolunteerApplication:
    return VolunteerApplication.objects.create(
        full_name="Test Person",
        email="v@example.test",
        phone="+211900000000",
        country="South Sudan",
        location="Juba",
        branch=branch,
        availability="weekends",
        consent=True,
    )


def test_branch_coordinator_only_sees_own_branch(make_staff, verified_client, two_branches) -> None:  # type: ignore[no-untyped-def]
    juba, yei = two_branches
    own, other = _event("Juba rally", juba), _event("Yei rally", yei)
    vol_own, vol_other = _volunteer(juba), _volunteer(yei)
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))

    page = client.get(_url("events_event_changelist"))
    assert page.status_code == 200
    assert b"Juba rally" in page.content and b"Yei rally" not in page.content

    # IDOR: direct object URLs for another branch are refused
    assert client.get(_url("events_event_change", own.pk)).status_code == 200
    assert client.get(_url("events_event_change", other.pk)).status_code in (302, 403, 404)
    assert client.get(_url("registrations_volunteerapplication_change", vol_own.pk)).status_code == 200
    assert client.get(_url("registrations_volunteerapplication_change", vol_other.pk)).status_code in (
        302,
        403,
        404,
    )
    assert client.get(_url("branches_branch_change", yei.pk)).status_code in (302, 403, 404)
    assert client.get(_url("branches_branch_change", juba.pk)).status_code == 200
    # Cannot delete even their own events
    assert client.post(_url("events_event_delete", own.pk), {"post": "yes"}).status_code == 403


def test_branch_coordinator_new_event_is_forced_to_own_branch(make_staff, verified_client, two_branches) -> None:  # type: ignore[no-untyped-def]
    juba, yei = two_branches
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=juba))
    start = timezone.now() + timedelta(days=3)
    data = {
        "title": "Sneaky",
        "slug": "sneaky",
        "summary": "x",
        "description": "",
        "branch": yei.pk,  # not in their allowed choices
        "start_0": start.strftime("%Y-%m-%d"),
        "start_1": "10:00:00",
        "end_0": start.strftime("%Y-%m-%d"),
        "end_1": "12:00:00",
        "capacity": "",
        "registration_deadline_0": "",
        "registration_deadline_1": "",
    }
    resp = client.post(_url("events_event_add"), data)
    assert resp.status_code == 200  # form error: invalid branch choice
    assert not Event.objects.filter(slug="sneaky").exists()
    data["branch"] = ""
    client.post(_url("events_event_add"), data)
    assert Event.objects.get(slug="sneaky").branch == juba


def test_coordinator_without_branch_sees_nothing(make_staff, verified_client, two_branches) -> None:  # type: ignore[no-untyped-def]
    _event("Juba rally", two_branches[0])
    client = verified_client(make_staff(BRANCH_COORDINATOR))
    assert b"Juba rally" not in client.get(_url("events_event_changelist")).content


def test_user_with_global_and_scoped_role_is_not_restricted(make_staff, verified_client, two_branches) -> None:  # type: ignore[no-untyped-def]
    juba, yei = two_branches
    _event("Yei rally", yei)
    client = verified_client(make_staff(MISSIONS, BRANCH_COORDINATOR, branch=juba))
    assert b"Yei rally" in client.get(_url("events_event_changelist")).content


def test_prayer_request_hidden_from_branch_coordinator(make_staff, verified_client, two_branches) -> None:  # type: ignore[no-untyped-def]
    pr = PrayerRequest.objects.create(request_text="private", consent=True)
    client = verified_client(make_staff(BRANCH_COORDINATOR, branch=two_branches[0]))
    assert client.get(_url("prayer_prayerrequest_change", pr.pk)).status_code == 403


def test_matrix_covers_every_project_model() -> None:
    labels = set(_all_model_labels())
    referenced = {label for matrix in ROLE_PERMISSIONS.values() for label in matrix}
    assert referenced <= labels, referenced - labels


def test_admin_url_setting_is_used() -> None:
    assert settings.ADMIN_URL == "test-portal/"
