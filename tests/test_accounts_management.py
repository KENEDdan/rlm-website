"""Only the Super Admin can create, activate, change roles for, deactivate or delete accounts."""

from __future__ import annotations

import re
from datetime import timedelta
from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core import mail
from django.test import Client
from django.urls import URLPattern, URLResolver, get_resolver, reverse
from django.utils import timezone
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts import integrity, reauth, services
from accounts.guard import sanctioned
from accounts.models import Invitation, User
from accounts.roles import (
    ALL_ROLES,
    BRANCH_COORDINATOR,
    EXECUTIVE,
    FINANCE,
    FOUNDER,
    MEMBERSHIP,
)
from audit.models import AuditLog
from branches.models import Branch
from portal.models import DepartmentMembership
from tests.conftest import PASSWORD, format_token, totp_now

pytestmark = pytest.mark.django_db

P = "/" + settings.PORTAL_URL
NEW_PASSWORD = "Brand-New-Passw0rd!"  # pragma: allowlist secret (test-only value)


def _reauth(client: Client, user: User) -> None:
    # django-otp refuses a code already used in this time step (replay protection); tests run within
    # one 30-second step of the sign-in, so forget the last-used step first.
    TOTPDevice.objects.filter(user=user).update(
        last_t=-1, throttling_failure_count=0, throttling_failure_timestamp=None
    )
    device = TOTPDevice.objects.get(user=user, confirmed=True)
    resp = client.post(
        P + "accounts/confirm/", {"password": PASSWORD, "code": format_token(totp_now(device))}
    )
    assert resp.status_code == 302, resp.content[:300]


@pytest.fixture
def founder(make_staff):  # type: ignore[no-untyped-def]
    return make_staff(FOUNDER, superuser=True, email="founder@example.test")


@pytest.fixture
def founder_client(founder, verified_client):  # type: ignore[no-untyped-def]
    client = verified_client(founder)
    _reauth(client, founder)
    return client


def _invite_data(**over: Any) -> dict[str, Any]:
    data = {"full_name": "New Person", "email": "new.person@example.test", "dept_finance": "member"}
    data.update(over)
    return data


def _link_token() -> str:
    match = re.search(r"/invite/([A-Za-z0-9_-]+)/", mail.outbox[-1].body)
    assert match, mail.outbox[-1].body
    return match.group(1)


# ------------------------------------------------------------------ 1. no self-registration
def _all_patterns(resolver: Any = None, prefix: str = "") -> list[str]:
    resolver = resolver or get_resolver()
    out: list[str] = []
    for p in resolver.url_patterns:
        if isinstance(p, URLResolver):
            out += _all_patterns(p, prefix + str(p.pattern))
        elif isinstance(p, URLPattern):
            out.append(prefix + str(p.pattern))
    return out


def _concrete(pattern: str) -> str:
    path = pattern.lstrip("^").rstrip("$")
    path = re.sub(r"\(\?P<department>[^)]*\)", "finance", path)
    path = re.sub(r"\(\?P<[a-z_]+>[^)]*\)", "1", path)
    path = re.sub(r"<(?:int:)?pk>|<int:[a-z_]+>", "1", path)
    path = re.sub(r"<(?:str:|slug:|path:)?[a-z_]+>", "x", path)
    return "/" + path.replace("\\", "")


def test_no_unauthenticated_url_can_create_a_user(client: Client) -> None:
    before = User._base_manager.count()
    payload = {
        "email": "attacker@example.test",
        "username": "attacker@example.test",
        "password": PASSWORD,
        "password1": PASSWORD,
        "password2": PASSWORD,
        "full_name": "Attacker",
        "is_superuser": "on",
        "is_staff": "on",
        "consent": "on",
    }
    paths = {_concrete(p) for p in _all_patterns()}
    assert len(paths) > 40
    for path in sorted(paths):
        client.get(path)
        client.post(path, payload)
    assert User._base_manager.count() == before
    assert not User._base_manager.filter(email="attacker@example.test").exists()


def test_no_signup_or_social_login_routes_exist() -> None:
    joined = " ".join(_all_patterns()).lower()
    for word in (
        "signup",
        "sign-up",
        "register/staff",
        "social-auth",
        "socialaccount",
        "oauth",
        "accounts/register",
    ):
        assert word not in joined


def test_there_is_no_api() -> None:
    joined = " ".join(_all_patterns()).lower()
    assert "api/" not in joined


# ------------------------------------------------------------------ 2. Super Admin-only management
NON_SUPER_ROLES = [r for r in ALL_ROLES if r != FOUNDER]


@pytest.mark.parametrize("role", NON_SUPER_ROLES)
def test_other_roles_cannot_manage_accounts(role: str, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    branch = Branch.objects.first()
    actor = make_staff(role, branch=branch, heads={"finance"} if role == FINANCE else ())
    target = make_staff(MEMBERSHIP, email="target@example.test")
    snapshot = (target.is_active, target.is_superuser, set(target.groups.all()), target.branch_id)
    client = verified_client(actor)
    urls_get = [
        "accounts/",
        "accounts/invite/",
        "accounts/review/",
        "accounts/audit/",
        f"accounts/{target.pk}/",
        f"accounts/{target.pk}/roles/",
        "accounts/confirm/",
    ]
    for url in urls_get:
        assert client.get(P + url).status_code in (403, 404), url
    for action in ("deactivate", "reactivate", "reset_2fa", "force_password_reset", "unlock", "delete"):
        assert client.post(P + f"accounts/{target.pk}/{action}/").status_code in (403, 404), action
    assert client.post(P + f"accounts/{target.pk}/roles/", {"super_admin": "on"}).status_code in (403, 404)
    assert client.post(P + "accounts/invite/", _invite_data()).status_code in (403, 404)
    # Django admin: no user/group/permission management at all
    admin = "/" + settings.ADMIN_URL
    for url in (
        "accounts/user/",
        "accounts/user/add/",
        f"accounts/user/{target.pk}/change/",
        "auth/group/",
        "auth/group/add/",
    ):
        assert client.get(admin + url).status_code in (302, 403, 404), url
    client.post(
        admin + "accounts/user/add/",
        {"email": "x@example.test", "password1": PASSWORD, "password2": PASSWORD},
    )
    # nothing changed
    target.refresh_from_db()
    assert snapshot == (target.is_active, target.is_superuser, set(target.groups.all()), target.branch_id)
    assert not User.objects.filter(email__in=["x@example.test", "new.person@example.test"]).exists()


@pytest.mark.parametrize("role", NON_SUPER_ROLES)
def test_services_refuse_non_super_admins_even_if_a_view_forgot(role: str, make_staff, rf) -> None:  # type: ignore[no-untyped-def]
    actor = make_staff(role)
    target = make_staff(email="t@example.test")
    request = rf.post("/")
    request.user = actor
    request.session = {}
    reauth.mark_fresh(request)
    spec = services.RoleSpec(
        departments={"finance": True}, extra_roles=set(), branch_id=None, super_admin=True
    )
    from django.core.exceptions import PermissionDenied

    for call in (
        lambda: services.invite_user(request, email="z@example.test", full_name="Z", spec=spec),
        lambda: services.change_roles(request, target, spec),
        lambda: services.deactivate(request, target),
        lambda: services.soft_delete(request, target),
        lambda: services.reset_2fa(request, target),
        lambda: services.force_password_reset(request, target),
    ):
        with pytest.raises(PermissionDenied):
            call()
    target.refresh_from_db()
    assert target.is_active and not target.is_superuser and not target.memberships.exists()


def test_department_head_cannot_grant_roles(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    head = make_staff(FINANCE, heads={"finance"})
    target = make_staff(email="t@example.test")
    client = verified_client(head)
    client.post(P + f"accounts/{target.pk}/roles/", {"dept_finance": "head"})
    assert not DepartmentMembership.objects.filter(user=target).exists()


# ------------------------------------------------------------------ privilege escalation
def test_super_admin_cannot_edit_own_roles(founder, founder_client) -> None:  # type: ignore[no-untyped-def]
    assert founder_client.get(P + f"accounts/{founder.pk}/roles/").status_code == 403
    founder_client.post(P + f"accounts/{founder.pk}/deactivate/")
    founder.refresh_from_db()
    assert founder.is_active and founder.is_superuser


def test_only_super_admin_creates_super_admin_and_limit_applies(founder, founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    resp = founder_client.post(
        P + "accounts/invite/", _invite_data(email="deputy@example.test", super_admin="on")
    )
    assert resp.status_code == 302
    deputy = User._base_manager.get(email="deputy@example.test")
    assert deputy.is_superuser and not deputy.is_active  # pending until the invite is accepted
    with sanctioned("test"):
        deputy.is_active = True
        deputy.set_password(PASSWORD)
        deputy.save()
    resp = founder_client.post(
        P + "accounts/invite/", _invite_data(email="third@example.test", super_admin="on")
    )
    assert resp.status_code == 200 and b"maximum" in resp.content
    assert not User._base_manager.filter(email="third@example.test").exists()


def test_last_super_admin_cannot_be_demoted_deactivated_or_deleted(founder, make_staff, rf) -> None:  # type: ignore[no-untyped-def]
    from unittest import mock

    deputy = make_staff(FOUNDER, superuser=True, email="deputy@example.test")
    request = rf.post("/")
    request.user = deputy
    request.session = {}
    reauth.mark_fresh(request)
    services.deactivate(request, founder)  # allowed while another Super Admin remains
    founder.refresh_from_db()
    assert not founder.is_active
    assert services._is_last_super_admin(deputy)
    # Even if the actor check were somehow passed, the last Super Admin stays protected.
    no_role = services.RoleSpec(departments={}, extra_roles=set(), branch_id=None, super_admin=False)
    request.user = make_staff(email="someone@example.test")
    with mock.patch.object(services, "_require_super_admin"):
        for call in (
            lambda: services.deactivate(request, deputy),
            lambda: services.soft_delete(request, deputy),
            lambda: services.change_roles(request, deputy, no_role),
        ):
            with pytest.raises(services.AccountError):
                call()
    deputy.refresh_from_db()
    assert deputy.is_super_admin


def test_reauth_is_required(founder, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(founder)
    resp = client.get(P + "accounts/invite/")
    assert resp.status_code == 302 and "/accounts/confirm/" in resp["Location"]
    resp = client.post(P + "accounts/invite/", _invite_data())
    assert resp.status_code == 302 and "/accounts/confirm/" in resp["Location"]
    assert not User._base_manager.filter(email="new.person@example.test").exists()
    # wrong code -> still blocked, failure audited
    client.post(P + "accounts/confirm/", {"password": PASSWORD, "code": "000000"})
    assert AuditLog.objects.filter(action=AuditLog.Action.REAUTH_FAILED).exists()
    _reauth(client, founder)
    assert client.get(P + "accounts/invite/").status_code == 200


def test_reauth_expires(founder, founder_client) -> None:  # type: ignore[no-untyped-def]
    session = founder_client.session
    session[reauth.SESSION_KEY] -= settings.REAUTH_WINDOW_SECONDS + 5
    session.save()
    assert founder_client.get(P + "accounts/invite/").status_code == 302


# ------------------------------------------------------------------ 3. invites
def test_invite_flow_single_use_and_2fa_forced(founder_client) -> None:  # type: ignore[no-untyped-def]
    resp = founder_client.post(P + "accounts/invite/", _invite_data(dept_membership="head"))
    assert resp.status_code == 302
    user = User._base_manager.get(email="new.person@example.test")
    assert not user.is_active and not user.has_usable_password()
    assert set(user.memberships.values_list("department__code", "is_head")) == {
        ("finance", False),
        ("membership", True),
    }
    assert set(user.groups.values_list("name", flat=True)) == {FINANCE, MEMBERSHIP}
    message = mail.outbox[-1]
    assert message.to == ["new.person@example.test"]
    assert "password" not in message.subject.lower() or "choose" in message.subject.lower()
    assert PASSWORD not in message.body and NEW_PASSWORD not in message.body
    assert "Finance" not in message.body  # nothing sensitive (no roles) in the email
    token = _link_token()
    assert Invitation.objects.get(user=user).token_hash != token  # only the hash is stored

    invitee = Client()
    url = reverse("accounts:accept_invite", args=[token])
    assert invitee.get(url).status_code == 200
    resp = invitee.post(url, {"password1": "short", "password2": "short"})
    assert resp.status_code == 200  # validators apply
    resp = invitee.post(url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD})
    assert resp.status_code == 302 and resp["Location"].endswith("2fa/setup/")
    user.refresh_from_db()
    assert user.is_active and user.check_password(NEW_PASSWORD)
    # 2FA is forced: the portal is not reachable before enrolment
    assert invitee.get(P).status_code == 302
    assert "login" in invitee.get(P)["Location"]
    # single use / replay rejected
    assert Client().get(url).status_code == 404
    assert Client().post(url, {"password1": NEW_PASSWORD, "password2": NEW_PASSWORD}).status_code == 404
    assert AuditLog.objects.filter(action=AuditLog.Action.INVITE_ACCEPTED, object_id=str(user.pk)).exists()


def test_invite_expiry_and_revocation(founder, founder_client) -> None:  # type: ignore[no-untyped-def]
    founder_client.post(P + "accounts/invite/", _invite_data())
    token = _link_token()
    inv = Invitation.objects.get()
    Invitation.objects.filter(pk=inv.pk).update(expires_at=timezone.now() - timedelta(minutes=1))
    url = reverse("accounts:accept_invite", args=[token])
    expired = Client().get(url)
    assert expired.status_code == 404
    user = inv.user
    founder_client.post(P + f"accounts/{user.pk}/resend_invite/")
    new_token = _link_token()
    assert new_token != token
    founder_client.post(P + f"accounts/{user.pk}/revoke_invites/")
    revoked = Client().get(reverse("accounts:accept_invite", args=[new_token]))
    assert revoked.status_code == 404
    # identical response for unknown / expired / revoked tokens (no probing)
    unknown = Client().get(reverse("accounts:accept_invite", args=["nope"]))
    assert unknown.content == expired.content == revoked.content


def test_duplicate_invite_gives_generic_error(founder, founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    make_staff(email="exists@example.test")
    resp = founder_client.post(P + "accounts/invite/", _invite_data(email="exists@example.test"))
    assert resp.status_code == 200 and b"could not be created" in resp.content


def test_branch_coordinator_needs_branch(founder_client) -> None:  # type: ignore[no-untyped-def]
    resp = founder_client.post(P + "accounts/invite/", _invite_data(branch_coordinator="on"))
    assert resp.status_code == 200
    assert not User._base_manager.filter(email="new.person@example.test").exists()


# ------------------------------------------------------------------ 4. safeguards
def test_deactivation_kills_sessions_and_is_audited(founder_client, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    target = make_staff(MEMBERSHIP, email="leaver@example.test")
    their_client = verified_client(target)
    assert their_client.get(P).status_code == 302  # redirected to their dashboard
    assert their_client.get(P + "membership/").status_code == 200
    resp = founder_client.post(P + f"accounts/{target.pk}/deactivate/")
    assert resp.status_code == 302
    target.refresh_from_db()
    assert not target.is_active
    assert their_client.get(P + "membership/").status_code == 302  # signed out
    assert not any(str(s.get_decoded().get("_auth_user_id")) == str(target.pk) for s in Session.objects.all())
    entry = AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_CHANGE, object_id=str(target.pk)).latest(
        "timestamp"
    )
    assert entry.extra["changes"]["is_active"] == {"old": True, "new": False}
    assert entry.ip_address and entry.actor_email == "founder@example.test"
    assert AuditLog.objects.filter(action=AuditLog.Action.SESSIONS_KILLED, object_id=str(target.pk)).exists()


def test_role_change_audited_with_old_and_new_values(founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    target = make_staff(MEMBERSHIP, email="t@example.test")
    founder_client.post(P + f"accounts/{target.pk}/roles/", {"dept_finance": "head", "executive": "on"})
    assert set(target.groups.values_list("name", flat=True)) == {FINANCE, EXECUTIVE}
    entries = AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_CHANGE, extra__target_user_id=target.pk)
    kinds = {e.extra["kind"] for e in entries}
    assert {"groups", "department_membership"} <= kinds


def test_reset_2fa_and_force_password_reset(founder_client, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    target = make_staff(MEMBERSHIP, email="t@example.test")
    verified_client(target)
    founder_client.post(P + f"accounts/{target.pk}/reset_2fa/")
    assert not TOTPDevice.objects.filter(user=target).exists()
    founder_client.post(P + f"accounts/{target.pk}/force_password_reset/")
    target.refresh_from_db()
    assert not target.has_usable_password()
    assert Invitation.objects.filter(user=target, kind=Invitation.Kind.RESET).exists()
    assert PASSWORD not in mail.outbox[-1].body


def test_soft_delete_keeps_row_and_history(founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    target = make_staff(MEMBERSHIP, BRANCH_COORDINATOR, email="t@example.test", branch=Branch.objects.first())
    founder_client.post(P + f"accounts/{target.pk}/delete/")
    target.refresh_from_db()
    assert target.deleted_at and not target.is_active and not target.has_usable_password()
    assert not target.groups.exists() and not target.memberships.exists()
    assert AuditLog.objects.filter(object_id=str(target.pk), model="user").exists()


def test_unlock_clears_axes_lockout(founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    from axes.models import AccessAttempt

    target = make_staff(email="t@example.test")
    AccessAttempt.objects.create(
        username=target.email,
        ip_address="10.0.0.1",
        failures_since_start=9,
        get_data="",
        post_data="",
        http_accept="",
        path_info="",
        user_agent="",
    )
    founder_client.post(P + f"accounts/{target.pk}/unlock/")
    assert not AccessAttempt.objects.filter(username=target.email).exists()


def test_out_of_band_change_is_detected_and_alerts(founder, make_staff) -> None:  # type: ignore[no-untyped-def]
    target = make_staff(email="t@example.test")
    mail.outbox.clear()
    target.is_superuser = True  # e.g. someone in a Django shell
    target.save()
    entry = AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_OUT_OF_BAND).latest("timestamp")
    assert entry.extra["changes"]["is_superuser"] == {"old": False, "new": True}


def test_out_of_band_group_and_membership_changes_detected(make_staff, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    founder = make_staff(FOUNDER, superuser=True, email="f@example.test")
    target = make_staff(email="t@example.test")
    mail.outbox.clear()
    with django_capture_on_commit_callbacks(execute=True):
        target.groups.add(Group.objects.get(name=FINANCE))
        from portal.models import Department

        DepartmentMembership.objects.create(
            user=target, department=Department.objects.get(code="finance"), is_head=True
        )
    assert AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_OUT_OF_BAND).count() >= 2
    assert mail.outbox and mail.outbox[-1].to == [founder.email]
    assert "t@example.test" not in mail.outbox[-1].body


def test_integrity_check_catches_raw_sql(make_staff, django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    from django.db import connection

    make_staff(FOUNDER, superuser=True, email="f@example.test")
    target = make_staff(email="t@example.test")
    integrity.store_fingerprint()
    assert integrity.check_integrity() is True
    with connection.cursor() as cur:
        cur.execute("UPDATE accounts_user SET is_superuser = TRUE WHERE id = %s", [target.pk])
    mail.outbox.clear()
    assert integrity.check_integrity() is False
    assert mail.outbox
    assert AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_INTEGRITY).exists()
    assert integrity.check_integrity() is True  # re-baselined: reported once


def test_dormant_accounts_flagged_then_disabled(make_staff) -> None:  # type: ignore[no-untyped-def]
    founder = make_staff(FOUNDER, superuser=True, email="f@example.test")
    flag = make_staff(email="flag@example.test")
    old = make_staff(email="old@example.test")
    now = timezone.now()
    User.objects.filter(pk=flag.pk).update(last_login=now - timedelta(days=settings.DORMANT_FLAG_DAYS + 1))
    User.objects.filter(pk__in=[old.pk, founder.pk]).update(
        last_login=now - timedelta(days=settings.DORMANT_DISABLE_DAYS + 1)
    )
    result = services.dormant_sweep()
    flag.refresh_from_db()
    old.refresh_from_db()
    founder.refresh_from_db()
    assert flag.is_active and flag.dormant_flagged_at
    assert not old.is_active
    assert founder.is_active and founder.dormant_flagged_at  # Super Admins are flagged, never auto-disabled
    assert result == {"flagged": 2, "disabled": 1}


def test_access_review_and_export_is_audited(founder_client, make_staff) -> None:  # type: ignore[no-untyped-def]
    make_staff(MEMBERSHIP, email="m@example.test")
    page = founder_client.get(P + "accounts/review/")
    assert page.status_code == 200 and b"m@example.test" in page.content
    resp = founder_client.get(P + "accounts/review/?format=csv")
    assert resp["Content-Type"].startswith("text/csv")
    assert b"m@example.test" in resp.content
    assert AuditLog.objects.filter(action=AuditLog.Action.EXPORT, model="user").exists()


def test_invite_creation_is_rate_limited(founder_client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.INVITE_RATE = "2/h"
    codes = [
        founder_client.post(P + "accounts/invite/", _invite_data(email=f"p{i}@example.test")).status_code
        for i in range(4)
    ]
    assert codes[-1] == 429
