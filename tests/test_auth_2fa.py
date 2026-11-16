"""Staff authentication: hidden admin, mandatory TOTP, lockout, rate limits, open redirects."""

from __future__ import annotations

import pytest
from django.conf import settings
from django.test import Client, override_settings
from django_otp.plugins.otp_static.models import StaticDevice
from django_otp.plugins.otp_totp.models import TOTPDevice

from audit.models import AuditLog
from tests.conftest import PASSWORD, format_token, totp_now

pytestmark = pytest.mark.django_db

LOGIN = "/" + settings.ADMIN_URL + "account/login/"
VERIFY = "/" + settings.ADMIN_URL + "account/2fa/verify/"
SETUP = "/" + settings.ADMIN_URL + "account/2fa/setup/"


def test_default_admin_url_is_404(client: Client) -> None:
    assert client.get("/admin/").status_code == 404
    assert client.get("/admin/login/").status_code == 404


def test_obscure_admin_redirects_anonymous_to_staff_login(client: Client, admin_prefix: str) -> None:
    resp = client.get(admin_prefix, follow=True)
    assert resp.redirect_chain[-1][0].startswith(admin_prefix + "account/login/")
    assert b"Sign in" in resp.content


def test_staff_without_2fa_session_cannot_reach_admin(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    client.force_login(user)  # bypasses the 2FA flow on purpose
    resp = client.get(admin_prefix)
    assert resp.status_code == 302
    assert "/account/login/" in resp["Location"]
    # ...and the unverified session was destroyed
    assert "_auth_user_id" not in client.session


def test_password_alone_does_not_log_in(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    TOTPDevice.objects.create(user=user, name="x", confirmed=True)
    resp = client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert resp.status_code == 302 and resp["Location"].endswith("2fa/verify/")
    assert "_auth_user_id" not in client.session
    assert client.get(admin_prefix).status_code == 302


def test_first_login_forces_totp_enrolment_then_backup_codes(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    resp = client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert resp["Location"].endswith("2fa/setup/")
    page = client.get(SETUP)
    assert page.status_code == 200 and b"data:image/svg+xml;base64" in page.content
    device = TOTPDevice.objects.get(user=user, confirmed=False)
    resp = client.post(SETUP, {"code": format_token(totp_now(device))})
    assert resp.status_code == 302 and resp["Location"].endswith("backup-codes/")
    device.refresh_from_db()
    assert device.confirmed
    codes_page = client.get(resp["Location"])
    assert codes_page.status_code == 200
    assert StaticDevice.objects.get(user=user).token_set.count() == 10
    assert client.get(admin_prefix).status_code == 200
    assert AuditLog.objects.filter(action="2fa_setup", actor_id=user.pk).exists()
    assert AuditLog.objects.filter(action="login", actor_id=user.pk).exists()


def test_backup_code_works_once(client: Client, make_staff) -> None:  # type: ignore[no-untyped-def]
    from accounts.twofactor import regenerate_backup_codes

    user = make_staff(superuser=True)
    TOTPDevice.objects.create(user=user, name="x", confirmed=True)
    code = regenerate_backup_codes(user)[0]
    client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert client.post(VERIFY, {"code": code}).status_code == 302
    other = Client()
    other.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert other.post(VERIFY, {"code": code}).status_code == 200  # rejected, form redisplayed


def test_wrong_codes_expire_pending_login(client: Client, make_staff) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    device = TOTPDevice.objects.create(user=user, name="x", confirmed=True)
    client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    for _ in range(5):
        client.post(VERIFY, {"code": "000000"})
    # Even the right code no longer works: the pending login was discarded.
    resp = client.post(VERIFY, {"code": format_token(totp_now(device))})
    assert resp.status_code == 302 and resp["Location"].endswith("account/login/")
    assert AuditLog.objects.filter(action="2fa_failed").count() == 5


def test_non_staff_cannot_log_in(client: Client, django_user_model) -> None:  # type: ignore[no-untyped-def]
    user = django_user_model.objects.create_user(email="public@example.test", password=PASSWORD)
    resp = client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert resp.status_code == 200
    assert b"not allowed to sign in" in resp.content


def test_full_flow_reaches_admin(make_staff, verified_client, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(superuser=True))
    assert client.get(admin_prefix).status_code == 200


def test_open_redirect_is_blocked(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    device = TOTPDevice.objects.create(user=user, name="x", confirmed=True)
    client.post(LOGIN + "?next=https://evil.example/phish", {"username": user.email, "password": PASSWORD})
    resp = client.post(VERIFY, {"code": format_token(totp_now(device))})
    assert resp["Location"] == admin_prefix


@override_settings(AXES_FAILURE_LIMIT=3)
def test_lockout_after_repeated_failures(client: Client, make_staff) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(superuser=True)
    for _ in range(3):
        client.post(LOGIN, {"username": user.email, "password": "wrong-password"})
    resp = client.post(LOGIN, {"username": user.email, "password": PASSWORD})
    assert resp.status_code in (403, 429)
    assert b"Too many failed attempts" in resp.content
    assert AuditLog.objects.filter(action="login_failed").count() >= 3


@override_settings(LOGIN_RATE="3/m")
def test_login_is_rate_limited_per_ip(client: Client) -> None:
    statuses = [
        client.post(LOGIN, {"username": f"x{i}@example.test", "password": "x"}).status_code for i in range(5)
    ]
    assert 429 in statuses


def test_logout_requires_post(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(superuser=True))
    url = "/" + settings.ADMIN_URL + "account/logout/"
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 302
    assert client.get("/" + settings.ADMIN_URL).status_code == 302


def test_password_validators_enforce_length_and_complexity() -> None:
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError

    for weak in ["short1!", "alllowercaseletters", "Password1234"]:
        with pytest.raises(ValidationError):
            validate_password(weak)
    validate_password("Correct-Horse-Battery-9")


def test_argon2_is_the_default_hasher() -> None:
    from config.settings import base

    assert base.PASSWORD_HASHERS[0].endswith("Argon2PasswordHasher")


def test_reset_two_factor_removes_devices(make_staff) -> None:  # type: ignore[no-untyped-def]
    from accounts.twofactor import regenerate_backup_codes, reset_two_factor

    user = make_staff()
    TOTPDevice.objects.create(user=user, name="x", confirmed=True)
    regenerate_backup_codes(user)
    reset_two_factor(user)
    assert not TOTPDevice.objects.filter(user=user).exists()
    assert not StaticDevice.objects.filter(user=user).exists()
