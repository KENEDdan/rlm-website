"""Phase E: content apps, seeds, publishing rules, SEO, sitemaps."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from branches.models import Branch, Country
from core.models import SiteSettings
from events.models import Event
from leadership.models import Leader
from media_library.models import (
    Testimony as MediaTestimony,
)  # alias: a name starting with "Test" is collected by pytest
from media_library.models import Video, parse_youtube_id
from news.models import Post
from programs.models import Program
from resources.models import Resource

pytestmark = pytest.mark.django_db

PUBLIC_URLS = [
    "/",
    "/about/",
    "/leadership/",
    "/programs/",
    "/branches/",
    "/branches/juba/",
    "/branches/yei/",
    "/events/",
    "/events/past/",
    "/gallery/",
    "/gallery/videos/",
    "/gallery/reports/",
    "/testimonies/",
    "/resources/",
    "/news/",
    "/get-involved/",
    "/partner/",
    "/give/",
    "/give/pledge/",
    "/prayer/",
    "/contact/",
    "/newsletter/subscribe/",
    "/privacy/",
    "/terms/",
    "/sitemap.xml",
    "/robots.txt",
]


@pytest.mark.parametrize("url", PUBLIC_URLS)
def test_public_pages_render(client: Client, url: str) -> None:
    resp = client.get(url)
    assert resp.status_code == 200, url


def test_pages_have_seo_and_nonce_scripts(client: Client) -> None:
    resp = client.get("/")
    html = resp.content.decode()
    nonce = resp.wsgi_request.csp_nonce
    assert f'nonce="{nonce}"' in html
    assert '<link rel="canonical"' in html and 'property="og:image"' in html
    assert "application/ld+json" in html and '"@type"' in html
    assert "onclick=" not in html and "javascript:" not in html


def test_seeded_branches_have_no_contact_details() -> None:
    assert Country.objects.filter(code="SS").exists()
    for slug in ("juba", "yei"):
        b = Branch.objects.get(slug=slug)
        assert b.is_published
        assert not (b.contact_email or b.contact_phone or b.address)


def test_new_country_and_branch_need_no_code(client: Client) -> None:
    ke = Country.objects.create(name="Kenya", code="KE")
    Branch.objects.create(country=ke, name="Nairobi", slug="nairobi", is_published=True)
    assert b"Kenya" in client.get("/branches/").content
    assert client.get("/branches/nairobi/").status_code == 200


def test_leadership_only_confirmed_and_published(client: Client) -> None:
    founder = Leader.objects.get(name="Justine Malish Michael")
    assert founder.is_published and founder.confirmation_status == "confirmed"
    tbc = Leader.objects.exclude(pk=founder.pk)
    assert tbc.exists() and not tbc.filter(is_published=True).exists()
    assert all(leader.name == "To be confirmed by leadership" for leader in tbc)
    html = client.get("/leadership/").content
    assert b"Justine Malish Michael" in html and b"To be confirmed" not in html
    # published but NOT confirmed still stays hidden
    leader = tbc.first()
    leader.is_published = True
    leader.save()
    assert b"To be confirmed by leadership</h2>" not in client.get("/leadership/").content


def test_programs_seeded() -> None:
    assert Program.objects.published().count() >= 5


def test_unpublished_content_is_404(client: Client) -> None:
    Program.objects.create(title="Hidden", slug="hidden", summary="x", is_published=False)
    assert client.get("/programs/hidden/").status_code == 404
    juba = Branch.objects.get(slug="juba")
    juba.is_published = False
    juba.save()
    assert client.get("/branches/juba/").status_code == 404


def _event(**kw) -> Event:  # type: ignore[no-untyped-def]
    start = kw.pop("start", timezone.now() + timedelta(days=5))
    defaults = {
        "title": "Conf",
        "slug": "conf",
        "summary": "s",
        "start": start,
        "end": start + timedelta(hours=3),
        "is_published": True,
    }
    defaults.update(kw)
    return Event.objects.create(**defaults)


def test_event_upcoming_past_and_registration_logic() -> None:
    up = _event(registration_open=True, capacity=2)
    past = _event(slug="old", start=timezone.now() - timedelta(days=10), registration_open=True)
    assert list(Event.objects.upcoming()) == [up]
    assert list(Event.objects.past()) == [past]
    assert up.can_register and not past.can_register
    up.registration_deadline = timezone.now() - timedelta(minutes=1)
    assert not up.can_register
    closed = _event(slug="closed", registration_open=False)
    assert not closed.can_register
    unlimited = _event(slug="unl", registration_open=True)
    assert unlimited.spots_left is None and unlimited.can_register


def test_event_end_before_start_invalid() -> None:
    e = Event(title="x", slug="x", summary="x", start=timezone.now(), end=timezone.now() - timedelta(hours=1))
    with pytest.raises(ValidationError):
        e.clean()


def test_news_draft_scheduled_published(client: Client) -> None:
    now = timezone.now()
    Post.objects.create(title="Draft", slug="draft", summary="s", body="b", status="draft")
    Post.objects.create(title="Live", slug="live", summary="s", body="b", status="published", publish_at=now)
    Post.objects.create(
        title="Later",
        slug="later",
        summary="s",
        body="b",
        status="scheduled",
        publish_at=now + timedelta(days=1),
    )
    Post.objects.create(
        title="Due",
        slug="due",
        summary="s",
        body="b",
        status="scheduled",
        publish_at=now - timedelta(minutes=1),
    )
    assert set(Post.objects.published().values_list("slug", flat=True)) == {"live", "due"}
    assert client.get("/news/draft/").status_code == 404
    assert client.get("/news/later/").status_code == 404
    assert client.get("/news/live/").status_code == 200
    bad = Post(
        title="x", slug="x", summary="s", body="b", status="scheduled", publish_at=now - timedelta(days=1)
    )
    with pytest.raises(ValidationError):
        bad.clean()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
        ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ],
)
def test_parse_youtube_id(value: str, expected: str) -> None:
    assert parse_youtube_id(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "https://evil.example/watch?v=dQw4w9WgXcQ",
        "javascript:alert(1)",
        "https://youtube.com/watch?v=<script>",
        "x",
    ],
)
def test_parse_youtube_id_rejects_bad_input(value: str) -> None:
    with pytest.raises(ValidationError):
        parse_youtube_id(value)


def test_video_uses_nocookie_facade(client: Client) -> None:
    Video.objects.create(
        title="Worship night", slug="worship", youtube_url="https://youtu.be/dQw4w9WgXcQ", is_published=True
    )
    html = client.get("/gallery/videos/").content.decode()
    assert 'data-yt="dQw4w9WgXcQ"' in html and "<iframe" not in html
    assert "www.youtube-nocookie.com" in client.get("/").headers["Content-Security-Policy"]


def test_testimony_requires_consent_to_publish() -> None:
    t = MediaTestimony(title="Healed", slug="healed", body="...", is_published=True, consent_confirmed=False)
    with pytest.raises(ValidationError):
        t.clean()


def test_resources_search_and_filters(client: Client) -> None:
    Resource.objects.create(
        title="Rebuild the walls", slug="walls", kind="sermon", speaker="Pastor A", is_published=True
    )
    Resource.objects.create(title="Morning light", slug="light", kind="devotional", is_published=True)
    assert b"Rebuild the walls" in client.get("/resources/?q=walls").content
    assert b"Morning light" not in client.get("/resources/?kind=sermon").content
    partial = client.get("/resources/?q=morning", HTTP_HX_REQUEST="true")
    assert b"Morning light" in partial.content and b"<html" not in partial.content


def test_user_content_is_escaped(client: Client) -> None:
    Program.objects.create(
        title="<script>alert(1)</script>",
        slug="xss",
        summary="<img src=x onerror=alert(1)>",
        body="Hello\n\n## <b>Heading</b>",
        is_published=True,
    )
    html = client.get("/programs/xss/").content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html
    assert "<h2>&lt;b&gt;Heading&lt;/b&gt;</h2>" in html


def test_sitemap_lists_published_only(client: Client) -> None:
    Program.objects.create(title="Secret", slug="secret-prog", summary="x", is_published=False)
    xml = client.get("/sitemap.xml").content.decode()
    assert "/programs/discipleship/" in xml and "secret-prog" not in xml
    assert "/branches/juba/" in xml


def test_robots_points_to_sitemap(client: Client) -> None:
    body = client.get("/robots.txt").content.decode()
    assert "Sitemap: http://testserver/sitemap.xml" in body


def test_site_settings_singleton_and_whatsapp(client: Client) -> None:
    s = SiteSettings.get()
    s.whatsapp_number = "+211 912 000 000"
    s.save()
    assert SiteSettings.objects.count() == 1
    with pytest.raises(PermissionError):
        s.delete()
    assert b"https://wa.me/211912000000" in client.get("/").content


def test_placeholder_images_are_labelled(client: Client) -> None:
    html = client.get("/branches/").content.decode()
    assert "Placeholder image" in html


def test_analytics_only_after_consent_markup(client: Client) -> None:
    assert b"consent-banner" not in client.get("/").content
    s = SiteSettings.get()
    s.analytics_provider = "plausible"
    s.analytics_script_url = "https://plausible.io/js/script.js"
    s.analytics_site_id = "example.org"
    s.save()
    html = client.get("/").content.decode()
    assert "consent-banner" in html
    assert '<script src="https://plausible.io' not in html  # loaded by site.js only after consent


def test_admin_url_reverse_uses_setting() -> None:
    assert reverse("admin:index") == "/test-portal/"
