"""Sliders: hero slides, partners, testimony approval, the slider component markup and its permissions."""

from __future__ import annotations

import gzip
import io
import re
from datetime import timedelta
from pathlib import Path

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from PIL import Image

from accounts.roles import ALL_ROLES, FOUNDER, MEDIA, MEMBERSHIP
from audit.models import AuditLog
from branches.models import Branch, Country
from core.models import HERO_SLIDE_LIMIT, HeroSlide, Partner
from core.validators import validate_safe_link
from events.models import Event
from leadership.models import Leader
from media_library.models import Album, Photo
from media_library.models import Testimony as MediaTestimony  # "Test*" names are collected by pytest

pytestmark = pytest.mark.django_db


def _jpeg(size: tuple[int, int] = (1920, 900)) -> SimpleUploadedFile:
    buf = io.BytesIO()
    Image.new("RGB", size, (240, 101, 42)).save(buf, format="JPEG")
    return SimpleUploadedFile("slide.jpg", buf.getvalue(), content_type="image/jpeg")


def _slider(html: str, slider_id: str) -> str:
    """The markup of one slider (from its root to the next slider root or the end of the page)."""
    start = html.rindex("<div", 0, html.index(f'id="{slider_id}" data-slider'))
    ends = [
        i for i in (html.find('<div class="slider ', start + 1), html.find("</section>", start)) if i != -1
    ]
    return html[start : min(ends) if ends else len(html)]


# ------------------------------------------------------------------ link validation
GOOD_LINKS = [
    "/give/",
    "/events/youth-conference/?ref=hero#top",
    "https://www.youtube.com/@rlm",
    "https://x.org",
]
BAD_LINKS = [
    "javascript:alert(1)",
    "JaVaScRiPt:alert(1)",
    "java\tscript:alert(1)",
    " javascript:alert(1)",
    "data:text/html;base64,PHNjcmlwdD4=",
    "vbscript:msgbox(1)",
    "http://example.org/",
    "//evil.example/",
    "/\\evil.example/",
    "https://user:pass@example.org/",  # pragma: allowlist secret (test: credentials in links are rejected)
    "https:///nohost",
    "give/",
    "mailto:a@example.test",
    "/give/\n",
]


@pytest.mark.parametrize("link", GOOD_LINKS)
def test_safe_links_accepted(link: str) -> None:
    validate_safe_link(link)
    HeroSlide(title="t", button_text="Go", button_link=link).full_clean()


@pytest.mark.parametrize("link", BAD_LINKS)
def test_unsafe_links_rejected(link: str) -> None:
    with pytest.raises(ValidationError):
        validate_safe_link(link)
    with pytest.raises(ValidationError) as exc:
        HeroSlide(title="t", button_text="Go", button_link=link).full_clean()
    assert "button_link" in exc.value.message_dict
    with pytest.raises(ValidationError):
        Partner(name="p", logo="partners/x.png", website=link).full_clean()


def test_bad_link_saved_outside_forms_is_never_rendered(client: Client) -> None:
    HeroSlide.objects.all().delete()
    HeroSlide.objects.create(title="Sneaky", button_text="Click", button_link="javascript:alert(1)")
    html = client.get("/").content.decode()
    assert "Sneaky" in html and "javascript:" not in html and ">Click<" not in html


def test_slide_button_needs_both_text_and_link() -> None:
    with pytest.raises(ValidationError) as exc:
        HeroSlide(title="t", button_text="Give").full_clean()
    assert "button_link" in exc.value.message_dict
    with pytest.raises(ValidationError) as exc:
        HeroSlide(title="t", button_link="/give/").full_clean()
    assert "button_text" in exc.value.message_dict


def test_slide_end_must_follow_start() -> None:
    now = timezone.now()
    with pytest.raises(ValidationError) as exc:
        HeroSlide(title="t", start_at=now, end_at=now - timedelta(hours=1)).full_clean()
    assert "end_at" in exc.value.message_dict


# ------------------------------------------------------------------ which slides show
def test_first_slide_seeded_with_tagline_and_scripture(client: Client) -> None:
    first = HeroSlide.objects.live().first()
    assert first.title == "Rebuilding Lives. Reviving Generations." and first.show_scripture
    html = client.get("/").content.decode()
    assert '<h1 class="hero-title">Rebuilding Lives. Reviving Generations.</h1>' in html
    assert "Acts 15:16" in html


def test_only_active_slides_inside_their_dates(client: Client) -> None:
    now = timezone.now()
    HeroSlide.objects.create(title="Switched off", is_active=False)
    HeroSlide.objects.create(title="Not yet", start_at=now + timedelta(days=1))
    HeroSlide.objects.create(title="Already over", end_at=now - timedelta(minutes=1))
    HeroSlide.objects.create(
        title="Showing window", start_at=now - timedelta(days=1), end_at=now + timedelta(days=1)
    )
    assert set(HeroSlide.objects.live().values_list("title", flat=True)) == {
        "Rebuilding Lives. Reviving Generations.",
        "Showing window",
    }
    html = client.get("/").content.decode()
    assert "Showing window" in html
    assert not any(t in html for t in ("Switched off", "Not yet", "Already over"))


def test_home_shows_at_most_five_slides_in_order(client: Client) -> None:
    for i in range(7):
        HeroSlide.objects.create(title=f"Slide number {i}", order=10 + i)
    html = client.get("/").content.decode()
    hero = _slider(html, "hero")
    assert hero.count('aria-roledescription="slide"') == HERO_SLIDE_LIMIT
    assert "Slide number 3" in hero and "Slide number 4" not in hero
    assert hero.index("Rebuilding Lives") < hero.index("Slide number 0") < hero.index("Slide number 3")


def test_without_active_slides_the_static_hero_is_shown(client: Client) -> None:
    HeroSlide.objects.update(is_active=False)
    html = client.get("/").content.decode()
    assert 'id="hero"' not in html and "<h1" in html and "Reviving Generations." in html


def test_slide_text_is_escaped(client: Client) -> None:
    HeroSlide.objects.create(title="<script>alert(1)</script>", subtitle="<img src=x onerror=alert(1)>")
    html = client.get("/").content.decode()
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    assert "<img src=x" not in html


def test_hero_images_preloaded_first_lazy_rest(client: Client, tmp_path, settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    HeroSlide.objects.all().delete()
    for i in range(2):
        slide = HeroSlide(title=f"Photo slide {i}", image=_jpeg(), image_alt=f"Crowd {i}", order=i)
        slide.full_clean()
        slide.save()
    html = client.get("/").content.decode()
    assert re.search(
        r'<link rel="preload" as="image" imagesrcset="[^"]+_w480\.webp 480w[^"]*" imagesizes="100vw" fetchpriority="high">',
        html,
    )
    imgs = re.findall(r'<img [^>]*alt="Crowd \d"[^>]*>', html)
    assert len(imgs) == 2
    assert 'loading="eager"' in imgs[0] and 'fetchpriority="high"' in imgs[0]
    assert 'loading="lazy"' in imgs[1] and "srcset=" in imgs[1] and ".webp" in imgs[1]
    # Uploaded through the safe pipeline: random name, re-encoded, WebP renditions.
    name = HeroSlide.objects.first().image.name
    assert name.startswith("hero/") and "slide" not in Path(name).name
    assert (tmp_path / name.replace(".jpg", "_w1600.webp")).exists()


def test_hero_slide_rejects_non_image_upload() -> None:
    fake = SimpleUploadedFile("x.jpg", b"<?php echo 1; ?>", content_type="image/jpeg")
    with pytest.raises(ValidationError) as exc:
        HeroSlide(title="t", image=fake).full_clean()
    assert "image" in exc.value.message_dict


# ------------------------------------------------------------------ component markup and accessibility
def test_slider_accessibility_and_no_js_fallback_markup(client: Client) -> None:
    HeroSlide.objects.create(title="Second slide", order=5)
    html = client.get("/").content.decode()
    hero = _slider(html, "hero")
    assert 'role="region" aria-roledescription="carousel" aria-label="Welcome slideshow"' in hero
    assert 'data-autoplay="6000"' in hero
    assert 'role="group" aria-roledescription="slide" aria-label="1 of 2"' in hero
    assert 'aria-label="2 of 2"' in hero
    # No-JS: the track is a focusable scroll-snap strip; the controls are hidden until slider.js runs.
    assert 'class="slider-track" id="hero-track" data-slider-track tabindex="0" role="group"' in hero
    assert re.search(r'class="slider-controls" data-slider-controls hidden', hero)
    assert 'aria-live="off"' in hero  # autoplay: no announcements
    assert 'data-slider-play aria-label="Pause the slideshow"' in hero
    assert 'aria-controls="hero-track" aria-label="Previous slide"' in hero
    assert 'aria-label="Next slide"' in hero
    # Card carousels never autoplay and announce manual changes politely.
    programmes = _slider(html, "programmes")
    assert "data-autoplay" not in programmes and "data-slider-play" not in programmes
    assert 'aria-live="polite"' in programmes


def test_slider_markup_is_csp_safe(client: Client) -> None:
    html = client.get("/").content.decode()
    assert re.search(r"\son[a-z]+=", html) is None  # no inline event handlers
    assert ' style="' not in html  # strict style-src: no inline styles
    for tag in re.findall(r"<script[^>]*>", html):
        assert "nonce=" in tag
        assert "src=" in tag or "application/ld+json" in tag
    assert re.search(r'<script src="/static/js/slider[^"]*\.js" nonce="[^"]+" defer>', html)


def test_slider_js_budget_and_no_unsafe_apis() -> None:
    source = (settings.BASE_DIR / "static" / "js" / "slider.js").read_bytes()
    assert len(gzip.compress(source, 9)) < 10 * 1024
    text = source.decode()
    for banned in ("eval(", "new Function", "innerHTML", "outerHTML", "insertAdjacentHTML", "document.write"):
        assert banned not in text
    assert "prefers-reduced-motion" in text


# ------------------------------------------------------------------ what each carousel lists
def test_events_carousel_lists_only_published_upcoming(client: Client) -> None:
    now = timezone.now()
    common = {"summary": "x", "venue": "Hall A"}
    Event.objects.create(
        title="Open night",
        slug="open",
        start=now + timedelta(days=2),
        end=now + timedelta(days=2, hours=2),
        is_published=True,
        registration_open=True,
        **common,
    )
    Event.objects.create(
        title="Draft night",
        slug="draft",
        start=now + timedelta(days=3),
        end=now + timedelta(days=3, hours=2),
        is_published=False,
        **common,
    )
    Event.objects.create(
        title="Old night",
        slug="old",
        start=now - timedelta(days=3),
        end=now - timedelta(days=3, hours=-2),
        is_published=True,
        **common,
    )
    events = _slider(client.get("/").content.decode(), "events")
    assert "Open night" in events and "Hall A" in events and "/events/open/register/" in events
    assert "Draft night" not in events and "Old night" not in events


def test_branches_carousel_includes_new_branches_automatically(client: Client) -> None:
    country = Country.objects.create(name="Kenya", code="KE")
    Branch.objects.create(country=country, name="Nairobi", slug="nairobi", is_published=True)
    Branch.objects.create(country=country, name="Hidden", slug="hidden", is_published=False)
    branches = _slider(client.get("/").content.decode(), "branches")
    assert all(name in branches for name in ("Juba", "Yei", "Nairobi")) and "Hidden" not in branches


def test_leadership_slider_only_confirmed_and_published(client: Client) -> None:
    Leader.objects.create(
        name="Shown Leader", role_title="Pastor", is_published=True, confirmation_status="confirmed"
    )
    Leader.objects.create(name="Unconfirmed Leader", role_title="Elder", is_published=True)
    Leader.objects.create(name="Draft Leader", role_title="Deacon", confirmation_status="confirmed")
    leaders = _slider(client.get("/about/").content.decode(), "leaders")
    assert "Shown Leader" in leaders
    assert "Unconfirmed Leader" not in leaders and "Draft Leader" not in leaders


def test_partner_strip_only_with_published_partners(client: Client, tmp_path, settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    assert "data-marquee" not in client.get("/").content.decode()
    hidden = Partner(name="Unpublished Co", logo=_jpeg((400, 160)))
    hidden.save()
    assert "data-marquee" not in client.get("/").content.decode()
    shown = Partner(
        name="Friendly Church", logo=_jpeg((400, 160)), website="https://example.org/", is_published=True
    )
    shown.full_clean()
    shown.save()
    html = client.get("/").content.decode()
    assert "data-marquee" in html and "Friendly Church" in html and "Unpublished Co" not in html
    assert 'rel="noopener noreferrer"' in html
    assert "data-marquee-toggle hidden" in html  # pause button appears only when it animates (JS)


def test_gallery_slider_lightbox_and_thumbnails(client: Client, tmp_path, settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    album = Album.objects.create(title="Camp", slug="camp", is_published=True)
    for i in range(3):
        Photo.objects.create(
            album=album, image=_jpeg((1200, 800)), alt_text=f"Camp photo {i}", caption=f"Caption {i}", order=i
        )
    Photo.objects.create(
        album=album, image=_jpeg((1200, 800)), alt_text="Private photo", is_published=False, order=9
    )
    html = client.get("/gallery/camp/").content.decode()
    photos = _slider(html, "album-photos")
    assert photos.count('aria-roledescription="slide"') == 3 and "Private photo" not in html
    assert 'data-lightbox-open="0"' in photos and "Caption 1" in photos
    assert 'data-slider-thumbs="album-photos"' in html and 'href="#album-photos-slide-2"' in html
    assert re.search(r'<dialog class="lightbox" data-lightbox aria-label="Photo viewer">', html)
    assert 'data-lightbox-close aria-label="Close the photo viewer"' in html
    # No-JS: each photo still links to its full-size image.
    assert re.search(r'<a href="[^"]+_w1600\.webp" class="gallery-frame"', photos)


# ------------------------------------------------------------------ testimonies
def _testimony(**kw) -> MediaTestimony:  # type: ignore[no-untyped-def]
    data = {
        "title": "Healed",
        "slug": f"t-{MediaTestimony.objects.count()}",
        "body": "Praise God.",
        "person_display_name": "Mary Akol Deng",
        "consent_confirmed": True,
        "is_published": True,
        "subject_is_adult": True,
        "is_approved": True,
    }
    data.update(kw)
    return MediaTestimony.objects.create(**data)


def test_only_approved_testimonies_are_public(client: Client) -> None:
    _testimony(title="Approved story")
    _testimony(title="Awaiting approval", is_approved=False)
    _testimony(title="Unpublished story", is_published=False)
    _testimony(title="No consent story", consent_confirmed=False)
    for url in ("/", "/testimonies/"):
        html = client.get(url).content.decode()
        assert "Approved story" in html
        assert not any(t in html for t in ("Awaiting approval", "Unpublished story", "No consent story"))


def test_testimony_names_are_minimised_without_consent(client: Client) -> None:
    t = _testimony()
    assert t.public_name == "M. A. D."  # default: initials
    t.name_display = MediaTestimony.NameDisplay.FIRST_NAME
    assert t.public_name == "Mary"
    t.name_display = MediaTestimony.NameDisplay.FULL_NAME
    assert t.public_name == "Mary"  # no explicit consent: never more than the first name
    t.full_name_consent = True
    assert t.public_name == "Mary Akol Deng"
    t.name_display = MediaTestimony.NameDisplay.ANONYMOUS
    assert t.public_name == "Anonymous"
    t.name_display = MediaTestimony.NameDisplay.INITIALS
    t.save()
    html = client.get("/").content.decode()
    assert "M. A. D." in html and "Mary Akol Deng" not in html and "Akol" not in html


def test_testimony_rules_on_clean() -> None:
    with pytest.raises(ValidationError) as exc:
        MediaTestimony(title="x", slug="x", body="x", name_display="full").clean()
    assert "full_name_consent" in exc.value.message_dict
    with pytest.raises(ValidationError) as exc:
        MediaTestimony(title="x", slug="x", body="x", is_approved=True).clean()
    assert "is_approved" in exc.value.message_dict


# ------------------------------------------------------------------ permissions and audit
SLIDE_MODELS = ["heroslide", "partner"]


@pytest.mark.parametrize("model", SLIDE_MODELS)
@pytest.mark.parametrize("role", ALL_ROLES)
def test_only_founder_and_media_manage_slides(make_staff, role: str, model: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(role)
    allowed = role in (FOUNDER, MEDIA)
    for action in ("view", "add", "change", "delete"):
        assert user.has_perm(f"core.{action}_{model}") is allowed, (role, action, model)


def test_media_can_approve_testimonies_secretary_only_views(make_staff) -> None:  # type: ignore[no-untyped-def]
    assert make_staff(MEDIA).has_perm("media_library.change_testimony")
    secretary = make_staff(MEMBERSHIP)
    assert secretary.has_perm("media_library.view_testimony")
    assert not secretary.has_perm("media_library.change_testimony")


@pytest.mark.parametrize(("role", "expected"), [(MEDIA, 200), (FOUNDER, 200), (MEMBERSHIP, 403)])
def test_hero_slide_admin_access(make_staff, verified_client, role: str, expected: int) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(role))
    assert client.get(reverse("admin:core_heroslide_changelist")).status_code == expected
    assert client.get(reverse("admin:core_partner_changelist")).status_code == expected


def _slide_post(**overrides: str) -> dict[str, str]:
    data = {
        "title": "Join the conference",
        "subtitle": "Three days of revival.",
        "image_alt": "",
        "button_text": "Register",
        "button_link": "/events/",
        "order": "3",
        "is_active": "on",
        "start_at_0": "",
        "start_at_1": "",
        "end_at_0": "",
        "end_at_1": "",
    }
    data.update(overrides)
    return data


def test_media_adds_slide_in_admin_and_it_is_audited(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    user = make_staff(MEDIA)
    client = verified_client(user)
    add = reverse("admin:core_heroslide_add")
    page = client.get(add).content.decode()
    assert "data-slide-preview" in page and "rlm-slide-preview.js" in page
    resp = client.post(add, _slide_post())
    assert resp.status_code == 302
    slide = HeroSlide.objects.get(title="Join the conference")
    assert AuditLog.objects.filter(
        action="add", model="heroslide", object_id=str(slide.pk), actor_id=user.pk
    ).exists()
    resp = client.post(reverse("admin:core_heroslide_change", args=[slide.pk]), _slide_post(title="Renamed"))
    assert resp.status_code == 302
    assert AuditLog.objects.filter(action="change", model="heroslide", object_id=str(slide.pk)).exists()
    client.post(reverse("admin:core_heroslide_delete", args=[slide.pk]), {"post": "yes"})
    assert not HeroSlide.objects.filter(pk=slide.pk).exists()
    assert AuditLog.objects.filter(action="delete", model="heroslide", object_id=str(slide.pk)).exists()


def test_admin_rejects_javascript_link(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEDIA))
    resp = client.post(reverse("admin:core_heroslide_add"), _slide_post(button_link="javascript:alert(1)"))
    assert resp.status_code == 200 and b"secure link starting with https://" in resp.content
    assert not HeroSlide.objects.filter(title="Join the conference").exists()


def test_secretary_cannot_post_slides(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEMBERSHIP))
    assert client.post(reverse("admin:core_heroslide_add"), _slide_post()).status_code == 403
    assert not HeroSlide.objects.filter(title="Join the conference").exists()


def test_admin_warns_when_more_than_five_slides_active(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    for i in range(HERO_SLIDE_LIMIT):
        HeroSlide.objects.create(title=f"Extra {i}")
    client = verified_client(make_staff(MEDIA))
    resp = client.get(reverse("admin:core_heroslide_changelist"))
    assert b"shows only the first 5" in resp.content


def test_roles_group_has_slide_permissions_after_migrations() -> None:
    media = Group.objects.get(name=MEDIA)
    codenames = set(media.permissions.values_list("codename", flat=True))
    assert {
        "add_heroslide",
        "change_heroslide",
        "delete_heroslide",
        "view_heroslide",
        "add_partner",
    } <= codenames
