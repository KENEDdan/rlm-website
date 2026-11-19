"""Launch readiness: what is still a placeholder or unsafe before the site goes public.

Run ``manage.py launch_check``. Every check says what is wrong and exactly where to fix it. BLOCKER items
must be fixed before launch; WARNING items should be reviewed; OK items are shown with ``--all``.
"""

from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from django.conf import settings

BLOCKER, WARNING, OK = "BLOCKER", "WARNING", "OK"


@dataclass(frozen=True)
class Check:
    level: str
    area: str
    message: str
    fix: str = ""


CHECKS: list[Callable[[], list[Check]]] = []


def check(func: Callable[[], list[Check]]) -> Callable[[], list[Check]]:
    CHECKS.append(func)
    return func


def run_checks() -> list[Check]:
    results: list[Check] = []
    for func in CHECKS:
        results.extend(func())
    order = {BLOCKER: 0, WARNING: 1, OK: 2}
    return sorted(results, key=lambda c: order[c.level])


def _one(ok: bool, area: str, problem: str, fix: str, level: str = WARNING, good: str = "") -> list[Check]:
    return [Check(OK, area, good or f"{area}: ok")] if ok else [Check(level, area, problem, fix)]


# ------------------------------------------------------------------ content and identity
@check
def ministry_text() -> list[Check]:
    from .models import SiteSettings

    site = SiteSettings.load()
    placeholder = "placeholder" in f"{site.about_intro} {site.about_body}".lower()
    return _one(
        not placeholder and bool(site.about_intro),
        "About text",
        "The About text still contains placeholder wording.",
        "Admin > Site settings > About: replace with the official text from the brief.",
        BLOCKER,
    ) + _one(
        bool(site.vision and site.mission),
        "Vision and mission",
        "Vision and/or mission are empty (the home page hides the section).",
        "Admin > Site settings: fill in Vision and Mission.",
    )


@check
def legal_pages() -> list[Check]:
    from .models import Page

    results: list[Check] = []
    for slug, name in (("privacy", "Privacy policy"), ("terms", "Terms of use")):
        page = Page.objects.filter(slug=slug).first()
        reviewed = bool(
            page and page.is_published and page.last_reviewed and "draft" not in page.body.lower()[:200]
        )
        results += _one(
            reviewed,
            name,
            f"{name} is missing, unpublished, still marked 'Draft', or has no 'Last reviewed' date.",
            f"Admin > Pages > {name}: have leadership review it, remove the Draft heading, set Last reviewed.",
            BLOCKER,
        )
    return results


@check
def contacts() -> list[Check]:
    from .models import SiteSettings, SocialLink

    site = SiteSettings.load()
    return (
        _one(
            bool(site.notification_email),
            "Staff alerts",
            "No notification email: nobody is told about new prayer requests, volunteers or messages.",
            "Admin > Site settings > Notification email (a ministry inbox, not a personal one).",
            BLOCKER,
        )
        + _one(
            bool(site.public_email or site.public_phone),
            "Public contact",
            "No public email or phone is shown on the site.",
            "Admin > Site settings: Public email / Public phone.",
        )
        + _one(
            bool(site.whatsapp_number),
            "WhatsApp button",
            "No WhatsApp number: the floating WhatsApp button is hidden.",
            "Admin > Site settings > WhatsApp number (international format).",
        )
        + _one(
            SocialLink.objects.filter(is_published=True).exists(),
            "Social links",
            "No social media links are published.",
            "Admin > Social links: add Facebook, Instagram, TikTok, YouTube...",
        )
    )


@check
def branding() -> list[Check]:
    from .models import SiteSettings

    site = SiteSettings.load()
    return _one(
        bool(site.logo and site.logo_on_dark),
        "Logos",
        "The built-in logos are in use (fine if they are the official ones).",
        "Admin > Site settings > Logo / Logo on dark background (PNG with transparency).",
    )


@check
def leaders() -> list[Check]:
    from leadership.models import Leader

    pending = Leader.objects.filter(confirmation_status=Leader.Status.TO_BE_CONFIRMED).count()
    shown = Leader.objects.published().count()
    return _one(
        pending == 0,
        "Leadership",
        f"{pending} leader(s) are still 'To be confirmed by leadership' ({shown} shown on the site).",
        "Admin > Leaders: confirm names and roles with leadership, then set Confirmed + Published.",
    )


@check
def branches() -> list[Check]:
    from branches.models import Branch

    missing = [
        b.name
        for b in Branch.objects.filter(is_published=True)
        if not (b.contact_email or b.contact_phone) or not b.meeting_times
    ]
    return _one(
        not missing,
        "Branch details",
        f"Branches without contact details or meeting times: {', '.join(missing)}.",
        "Admin > Branches: add contact, address and meeting times.",
    )


@check
def demo_content() -> list[Check]:
    from events.models import Event
    from news.models import Post

    found = (
        Event.objects.filter(slug__startswith="demo-").exists()
        or Post.objects.filter(slug__startswith="demo-").exists()
    )
    return _one(
        not found,
        "Demo content",
        "Fake demo content (titles starting with 'DEMO') is still in the database.",
        "On the development PC: manage.py seed_demo --reset. Never load demo data on the server.",
        BLOCKER,
    )


@check
def giving() -> list[Check]:
    from giving.models import GivingSettings

    gs = GivingSettings.load()
    can_give = gs.has_bank_details or (gs.mobile_money_enabled and bool(gs.mobile_money_instructions))
    return _one(
        can_give,
        "Giving",
        "The Give page shows no way to give: no complete bank details and no mobile-money instructions.",
        "Finance: Admin > Giving settings (confirm bank details with the bank by phone first).",
    )


# ------------------------------------------------------------------ people and security
@check
def staff_security() -> list[Check]:
    from django_otp.plugins.otp_totp.models import TOTPDevice

    from accounts.models import User

    staff = User.objects.filter(is_staff=True, is_active=True)
    without_2fa = [u.email for u in staff if not TOTPDevice.objects.filter(user=u, confirmed=True).exists()]
    founders = staff.filter(is_superuser=True).count()
    return (
        _one(
            founders >= 1,
            "Founder account",
            "There is no active Founder (superuser) account.",
            "manage.py create_super_admin (docs/HANDOVER.md section 2).",
            BLOCKER,
        )
        + _one(
            founders <= 2,
            "Founder accounts",
            f"{founders} superuser accounts: keep it to the Founder and at most one deputy.",
            "Staff portal > Accounts & security: change their roles so only the Founder and one deputy are Super Admins.",
        )
        + _one(
            not without_2fa,
            "Two-factor sign-in",
            f"{len(without_2fa)} staff account(s) have not finished authenticator setup.",
            "Ask them to sign in now (whoever signs in first enrols the authenticator).",
        )
    )


@check
def configuration() -> list[Check]:
    backend = settings.EMAIL_BACKEND
    real_email = "smtp" in backend and settings.EMAIL_HOST not in ("", "mailpit", "localhost")
    return (
        _one(
            not settings.DEBUG,
            "Debug mode",
            "DEBUG is on: error pages would show internal details.",
            "Use config.settings.prod on the server.",
            BLOCKER,
        )
        + _one(
            settings.SITE_URL.startswith("https://"),
            "Site address",
            f"SITE_URL is {settings.SITE_URL!r}: links in emails must use the real https:// address.",
            "Server .env: SITE_URL=https://<domain>.",
            BLOCKER,
        )
        + _one(
            settings.TURNSTILE_ENABLED and bool(settings.TURNSTILE_SECRET_KEY),
            "Spam protection",
            "Cloudflare Turnstile is not configured.",
            "Server .env: TURNSTILE_SITE_KEY / TURNSTILE_SECRET_KEY.",
            BLOCKER,
        )
        + _one(
            real_email,
            "Email delivery",
            f"Emails are not sent through a real mail server ({backend.rsplit('.', 1)[-1]}, {settings.EMAIL_HOST}).",
            "Server .env: EMAIL_HOST/USER/PASSWORD of the transactional provider; SPF/DKIM/DMARC in DNS.",
            BLOCKER,
        )
        + _one(
            bool(os.environ.get("BACKUP_AGE_RECIPIENT")),
            "Backups",
            "No backup encryption key is configured (BACKUP_AGE_RECIPIENT).",
            "docs/DEPLOYMENT.md section 3 'Backup key pair'; then test a restore.",
        )
        + _one(
            bool(settings.SENTRY_DSN),
            "Error reporting",
            "Sentry is not configured; errors are only in the server logs.",
            "Optional: SENTRY_DSN in the server .env.",
        )
    )


@check
def retention() -> list[Check]:
    from .models import SiteSettings

    site = SiteSettings.load()
    keep_forever = [
        name
        for name, days in (
            ("prayer requests", site.retention_prayer_days),
            ("contact messages", site.retention_contact_days),
            ("volunteer applications", site.retention_volunteer_days),
        )
        if not days
    ]
    return _one(
        not keep_forever,
        "Data retention",
        f"Kept forever (retention 0): {', '.join(keep_forever)}.",
        "Admin > Site settings > retention periods (privacy policy must match).",
    )
