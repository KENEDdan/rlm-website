"""Part 3: hero backgrounds (theme colour / photo / video), fallbacks, readability, preview, publish, revert."""

from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.roles import MEMBERSHIP, TECHNICAL
from core.hero import contrast_ratio
from core.models import ContentVersion, HeroSettings, HeroSlide

from . import upload_samples as s

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL
HERO = P + "website/hero/"


@pytest.fixture(autouse=True)
def _media(tmp_path: Any, settings: Any) -> None:
    settings.MEDIA_ROOT = tmp_path


@pytest.fixture(autouse=True)
def _no_slides() -> None:
    HeroSlide.objects.all().delete()


def _live(**fields: Any) -> HeroSettings:
    live = HeroSettings.live()
    for k, v in fields.items():
        setattr(live, k, v)
    live.save()
    return live


def test_default_is_theme_colour(client: Client) -> None:
    live = HeroSettings.live()
    assert live.background_type == "theme" and live.effective_background == "theme"
    html = client.get("/").content.decode()
    assert 'data-hero-bg="theme"' in html and "hero-glow" in html
    assert "<video" not in html
    assert live.title in html


def test_photo_without_a_photo_falls_back_to_theme(client: Client) -> None:
    _live(background_type="photo")
    assert HeroSettings.live().effective_background == "theme"
    assert 'data-hero-bg="theme"' in client.get("/").content.decode()


def test_photo_background_with_focal_point_and_overlay(client: Client) -> None:
    _live(background_type="photo", image=SimpleUploadedFile("h.jpg", s.jpeg(1800, 900)), focal_x=30,
          focal_y=70, overlay_opacity=60)  # fmt: skip
    html = client.get("/").content.decode()
    assert 'data-hero-bg="photo"' in html
    assert "object-position:30% 70%" in html and "rgba(10,10,10,0.60)" in html
    assert 'srcset="' in html and "_w1600.webp 1600w" in html  # responsive renditions
    assert '<link rel="preload" as="image"' in html


def test_overlay_is_limited_to_80_percent() -> None:
    hero = HeroSettings.draft()
    hero.overlay_opacity = 90
    with pytest.raises(ValidationError):
        hero.full_clean()


def test_video_requires_a_poster() -> None:
    hero = HeroSettings.draft()
    hero.background_type = "video"
    hero.video = SimpleUploadedFile("loop.mp4", s.mp4())
    with pytest.raises(ValidationError) as exc:
        hero.full_clean()
    assert "video_poster" in exc.value.message_dict


def test_video_without_poster_or_file_falls_back_to_theme() -> None:
    hero = HeroSettings.draft()
    hero.background_type = "video"
    assert hero.effective_background == "theme"


def test_video_markup_is_silent_lazy_and_poster_first(client: Client) -> None:
    _live(background_type="video", video=SimpleUploadedFile("loop.mp4", s.mp4()),
          video_poster=SimpleUploadedFile("p.jpg", s.jpeg(1800, 900)))  # fmt: skip
    html = client.get("/").content.decode()
    assert 'data-hero-bg="video"' in html
    video = html[html.index("<video") : html.index("</video>")]
    for attr in ("muted", "loop", "playsinline", 'preload="none"', "poster="):
        assert attr in video
    assert "autoplay" not in video and " src=" not in video  # no source until the script allows it
    assert 'data-src="/uploads/hero-video/' in video and 'type="video/mp4"' in video
    assert "js/hero-video.js" in html and "Pause background video" in html
    assert 'class="hero-slide-img' in html  # poster image is also the no-JS / slow-connection fallback


def test_video_script_honours_motion_data_saver_and_slow_connections() -> None:
    js = (settings.BASE_DIR / "static" / "js" / "hero-video.js").read_text()
    for needle in ("prefers-reduced-motion", "saveData", "effectiveType", "requestIdleCallback", '"load"'):
        assert needle in js


def test_csp_serves_media_only_from_our_storage(client: Client) -> None:
    csp = client.get("/")["Content-Security-Policy"]
    assert "media-src 'self'" in csp


def test_contrast_check() -> None:
    assert contrast_ratio("theme", None, 0, "light") > 15  # white on brand black
    assert contrast_ratio("theme", None, 0, "dark") < 4.5  # black on black: warn
    assert contrast_ratio("photo", 0.9, 10, "light") < 4.5  # bright photo, light overlay: warn
    assert contrast_ratio("photo", 0.9, 80, "light") >= 4.5  # strong overlay fixes it
    hero = _live(
        background_type="photo", image=SimpleUploadedFile("w.png", s.png(1800, 900)), overlay_opacity=0
    )
    assert hero.image_luminance is not None and hero.image_luminance > 0.1
    from core.hero import contrast_message

    assert "Readability warning" in contrast_message(hero) or hero.contrast_ok


def test_white_photo_triggers_readability_warning() -> None:
    from io import BytesIO

    from PIL import Image

    buf = BytesIO()
    Image.new("RGB", (1800, 900), "white").save(buf, format="JPEG")
    hero = _live(
        background_type="photo", image=SimpleUploadedFile("w.jpg", buf.getvalue()), overlay_opacity=0
    )
    assert hero.image_luminance > 0.9 and not hero.contrast_ok


def test_two_buttons_with_validated_links(client: Client) -> None:
    hero = HeroSettings.draft()
    hero.button_text, hero.button_link = "Give", "/give/"
    hero.button2_text, hero.button2_link = "Evil", "javascript:alert(1)"
    with pytest.raises(ValidationError) as exc:
        hero.full_clean()
    assert "button2_link" in exc.value.message_dict
    _live(button_text="Give", button_link="/give/", button2_text="Sneaky", button2_link="javascript:alert(1)")
    html = client.get("/").content.decode()
    assert 'href="/give/"' in html and "javascript:" not in html and ">Sneaky<" not in html


def test_alignment_and_text_colour_presets(client: Client) -> None:
    _live(text_align="center", text_tone="dark")
    html = client.get("/").content.decode()
    assert "hero-align-center" in html and "hero-tone-dark" in html


# ------------------------------------------------------------------ portal: draft, preview, publish, revert
def _form(**over: Any) -> dict[str, Any]:
    data = {
        "title": "Draft headline", "subtitle": "Draft sub", "background_type": "theme", "image_alt": "",
        "focal_x": 50, "focal_y": 50, "overlay_opacity": 45, "text_align": "left", "text_tone": "light",
        "button_text": "", "button_link": "", "button2_text": "", "button2_link": "", "action": "save",
    }  # fmt: skip
    data.update(over)
    return data


def test_preview_before_publish_then_revert(make_staff: Any, verified_client: Any, client: Client) -> None:
    tech = verified_client(make_staff(TECHNICAL))
    before = HeroSettings.live().title
    assert tech.post(HERO, _form()).status_code == 302
    assert HeroSettings.draft().title == "Draft headline"
    assert "Draft headline" not in client.get("/").content.decode()  # visitors still see the live hero
    preview = tech.get(P + "website/hero/preview/")
    assert preview.status_code == 200 and "Draft headline" in preview.content.decode()
    assert "noindex" in preview["X-Robots-Tag"]
    page = tech.get(HERO).content.decode()
    assert "Live preview of the draft" in page and "js/hero-editor.js" in page
    tech.post(HERO, {"action": "publish"})
    assert "Draft headline" in client.get("/").content.decode()
    assert ContentVersion.objects.filter(action="publish").exists()
    tech.post(HERO, {"action": "revert"})
    assert HeroSettings.live().title == before
    assert "Draft headline" not in client.get("/").content.decode()


def test_upload_rules_apply_in_the_portal_form(make_staff: Any, verified_client: Any) -> None:
    tech = verified_client(make_staff(TECHNICAL))
    resp = tech.post(
        HERO, _form(background_type="photo", image=SimpleUploadedFile("small.jpg", s.jpeg(800, 400)))
    )
    assert resp.status_code == 200 and "at least 1600" in resp.content.decode()
    resp = tech.post(HERO, _form(background_type="video", video=SimpleUploadedFile("long.mp4", s.mp4(seconds=25)),
                                 video_poster=SimpleUploadedFile("p.jpg", s.jpeg())))  # fmt: skip
    assert resp.status_code == 200 and "seconds long" in resp.content.decode()
    assert HeroSettings.draft().background_type == "theme"


def test_preview_of_a_switched_off_slide(make_staff: Any, verified_client: Any, client: Client) -> None:
    slide = HeroSlide.objects.create(title="Hidden slide", is_active=False)
    tech = verified_client(make_staff(TECHNICAL))
    assert "Hidden slide" in tech.get(P + f"website/hero/preview/?slide={slide.pk}").content.decode()
    assert "Hidden slide" not in client.get("/").content.decode()


def test_hero_editor_is_technical_team_only(make_staff: Any, verified_client: Any, client: Client) -> None:
    other = verified_client(make_staff(MEMBERSHIP))
    assert other.get(HERO).status_code == 403
    assert other.post(HERO, {"action": "publish"}).status_code == 403
    assert client.get(P + "website/hero/preview/").status_code == 302  # anonymous: to sign-in


def test_slides_support_backgrounds_and_fall_back(client: Client) -> None:
    HeroSlide.objects.create(title="Photo slide", background_type="photo", order=1)
    html = client.get("/").content.decode()
    assert "Photo slide" in html and 'data-hero-bg="theme"' in html  # no photo: theme colour
