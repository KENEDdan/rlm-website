"""Phase L: launch readiness report and Founder account creation."""

from __future__ import annotations

import io
from datetime import date
from unittest import mock

import pytest
from django.core.management import CommandError, call_command
from django.test import override_settings
from django_otp.plugins.otp_totp.models import TOTPDevice

from accounts.models import User
from accounts.roles import FOUNDER
from audit.models import AuditLog
from core.launch import BLOCKER, OK, run_checks
from core.models import Page, SiteSettings, SocialLink

pytestmark = pytest.mark.django_db

STRONG = "Correct-Horse-Battery-9!"
READY_SETTINGS = {
    "DEBUG": False,
    "SITE_URL": "https://rlm.example.org",
    "TURNSTILE_ENABLED": True,
    "TURNSTILE_SITE_KEY": "site",
    "TURNSTILE_SECRET_KEY": "secret",  # pragma: allowlist secret
    "EMAIL_BACKEND": "django.core.mail.backends.smtp.EmailBackend",
    "EMAIL_HOST": "smtp.example.org",
    "SENTRY_DSN": "https://key@sentry.example.org/1",
}


def _areas(level: str) -> set[str]:
    return {c.area for c in run_checks() if c.level == level}


def _make_site_ready() -> None:
    site = SiteSettings.load()
    site.about_intro = "Official introduction."
    site.about_body = "Official story."
    site.vision, site.mission = "Vision", "Mission"
    site.notification_email = "office@example.org"
    site.public_email = "info@example.org"
    site.whatsapp_number = "+211 900 000 000"
    site.save()
    for slug in ("privacy", "terms"):
        page = Page.objects.get(slug=slug)
        page.body = "## Who we are\nReviewed text."
        page.last_reviewed = date(2026, 11, 1)
        page.is_published = True
        page.save()
    SocialLink.objects.create(platform="facebook", url="https://facebook.com/example")
    founder = User.objects.create_superuser(email="founder@example.org", password=STRONG, full_name="Founder")
    TOTPDevice.objects.create(user=founder, name="app", confirmed=True)


def test_fresh_install_is_not_ready_and_says_why() -> None:
    blockers = _areas(BLOCKER)
    assert {"About text", "Privacy policy", "Terms of use", "Staff alerts", "Founder account"} <= blockers
    for item in run_checks():
        if item.level != OK:
            assert item.fix, item  # every problem comes with instructions


@override_settings(**READY_SETTINGS)
def test_ready_site_has_no_blockers(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BACKUP_AGE_RECIPIENT", "age1example")
    _make_site_ready()
    assert _areas(BLOCKER) == set()
    call_command("launch_check", "--strict", stdout=io.StringIO())  # does not raise


@override_settings(**READY_SETTINGS)
def test_demo_content_and_draft_policy_are_blockers() -> None:
    from events.models import Event

    _make_site_ready()
    Event.objects.create(
        title="DEMO", slug="demo-x", summary="x", start="2030-01-01T10:00Z", end="2030-01-01T12:00Z"
    )
    privacy = Page.objects.get(slug="privacy")
    privacy.body = "## Draft: to be reviewed\n..."
    privacy.save()
    assert {"Demo content", "Privacy policy"} <= _areas(BLOCKER)


@override_settings(**READY_SETTINGS)
def test_staff_without_2fa_and_too_many_superusers_are_flagged() -> None:
    _make_site_ready()
    User.objects.create_user(email="sec@example.org", password=STRONG, is_staff=True)
    for i in range(2):
        User.objects.create_superuser(email=f"extra{i}@example.org", password=STRONG)
    warnings = {c.area: c.message for c in run_checks() if c.level != OK}
    assert "3 staff account(s)" in warnings["Two-factor sign-in"]
    assert "3 superuser accounts" in warnings["Founder accounts"]


def test_strict_mode_fails_with_blockers() -> None:
    out = io.StringIO()
    with pytest.raises(CommandError, match="Not ready"):
        call_command("launch_check", "--strict", stdout=out)
    assert "[BLOCKER]" in out.getvalue() and "fix:" in out.getvalue()


# ------------------------------------------------------------------ create_super_admin (bootstrap)
def _run_bootstrap(*passwords: str, email: str = "Founder@Example.org") -> str:
    out = io.StringIO()
    with mock.patch("getpass.getpass", side_effect=list(passwords)):
        call_command(
            "create_super_admin", "--email", email, "--name", "Justine Founder", stdout=out, stderr=out
        )
    return out.getvalue()


def test_create_super_admin_makes_superuser_in_founder_role_and_audits() -> None:
    output = _run_bootstrap(STRONG, STRONG)
    user = User.objects.get(email="founder@example.org")
    assert user.is_superuser and user.is_staff and user.check_password(STRONG)
    assert user.groups.filter(name=FOUNDER).exists()
    entry = AuditLog.objects.filter(
        action=AuditLog.Action.ACCOUNT_CHANGE, actor_email="system:create_super_admin", extra__kind="user"
    ).first()
    assert entry is not None and entry.extra["changes"]["created"]["new"] is True
    assert not AuditLog.objects.filter(action=AuditLog.Action.ACCOUNT_OUT_OF_BAND).exists()
    assert "authenticator" in output


def test_create_super_admin_enforces_password_rules_and_creates_nothing_on_failure() -> None:
    with pytest.raises(CommandError, match="No valid password"):
        _run_bootstrap("short", "short", "password1234", "password1234", "Mismatch-Pass-1!", "Other-Pass-2!")
    assert not User.objects.exists()


def test_create_super_admin_refuses_when_a_super_admin_exists_or_bad_email() -> None:
    _run_bootstrap(STRONG, STRONG)
    with pytest.raises(CommandError, match="already exists"):
        _run_bootstrap(STRONG, STRONG, email="second@example.org")
    assert User.objects.filter(is_superuser=True).count() == 1
    User.objects.all().delete()
    with pytest.raises(CommandError, match="not a valid email"):
        _run_bootstrap(STRONG, STRONG, email="not-an-email")
