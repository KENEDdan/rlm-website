"""Privacy policy and cookies (rule 13): only necessary, session-length cookies; facts generated from settings;
consent can be withdrawn; the improved draft policy never overwrites leadership's edits."""

from __future__ import annotations

import importlib

import pytest
from django.apps import apps as global_apps
from django.conf import settings
from django.test import Client

from core.models import Page, SiteSettings

pytestmark = pytest.mark.django_db

migration = importlib.import_module("core.migrations.0005_privacy_policy_v2")


def _cookies(response) -> dict:  # type: ignore[no-untyped-def]
    return dict(response.cookies.items())


@pytest.mark.parametrize("url", ["/", "/events/", "/news/", "/privacy/", "/activities/"])
def test_pages_without_forms_set_no_cookies(client: Client, url: str) -> None:
    assert _cookies(client.get(url)) == {}


def test_form_pages_set_only_a_session_length_security_cookie(client: Client) -> None:
    cookies = _cookies(client.get("/contact/"))
    assert set(cookies) == {settings.CSRF_COOKIE_NAME}
    morsel = cookies[settings.CSRF_COOKIE_NAME]
    assert not morsel["expires"] and not morsel["max-age"]  # deleted when the browser closes
    assert morsel["httponly"] and morsel["samesite"] == "Lax"


def test_privacy_page_lists_real_cookies_and_live_retention(client: Client) -> None:
    site = SiteSettings.load()
    site.retention_prayer_days = 90
    site.save()
    html = client.get("/privacy/").content.decode()
    assert settings.CSRF_COOKIE_NAME in html and settings.SESSION_COOKIE_NAME in html
    assert "Prayer requests: deleted automatically after 90 days" in html
    assert "Who else sees it" in html and "Children" in html  # improved draft text applied
    assert "We do not use visitor statistics." in html


def test_privacy_choices_offered_only_when_analytics_is_enabled(client: Client) -> None:
    html = client.get("/").content.decode()
    assert "data-consent-reset" not in html and "consent-banner" not in html
    site = SiteSettings.load()
    site.analytics_provider = "plausible"
    site.analytics_script_url = "https://stats.example.org/js/script.js"
    site.analytics_site_id = "example.org"
    site.save()
    home = client.get("/").content.decode()
    assert "consent-banner" in home and "data-consent-reset" in home  # footer "Privacy choices"
    assert "Change your privacy choices" in client.get("/privacy/").content.decode()
    assert "stats.example.org" not in home.split("analytics-config")[0]  # script never loads before consent


def test_improved_policy_replaces_only_the_untouched_seed() -> None:
    page = Page.objects.get(slug="privacy")
    page.body = "## Draft: seed\n" + migration.ORIGINAL_MARKER
    page.save()
    migration.update_policy(global_apps, None)
    page.refresh_from_db()
    assert page.body == migration.PRIVACY_V2

    page.body = "Our official, reviewed privacy policy."
    page.save()
    migration.update_policy(global_apps, None)
    page.refresh_from_db()
    assert page.body == "Our official, reviewed privacy policy."
