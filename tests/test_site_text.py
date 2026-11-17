"""Editable page text and form options: everything visitors read can be changed in the admin."""

from __future__ import annotations

import pytest
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client

from accounts.roles import MEDIA, PROGRAMS, SECRETARY
from contact.models import ContactMessage
from core.models import FormOption, PageText
from core.page_texts import FORM_OPTION_DEFAULTS, PAGE_TEXT_DEFAULTS
from core.site_text import ensure_defaults, option_choices, option_label, page_text
from registrations.models import VolunteerApplication

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ seeding
def test_every_default_is_seeded_and_edits_survive_a_resync() -> None:
    assert set(PageText.objects.values_list("key", flat=True)) == set(PAGE_TEXT_DEFAULTS)
    for list_name, options in FORM_OPTION_DEFAULTS.items():
        assert FormOption.objects.filter(list=list_name).count() == len(options)
    PageText.objects.filter(key="events").update(heading="Edited heading")
    FormOption.objects.filter(list="contact_topic", value="media").update(label="Press")
    ensure_defaults()
    assert PageText.objects.get(key="events").heading == "Edited heading"
    assert FormOption.objects.get(list="contact_topic", value="media").label == "Press"


def test_missing_row_falls_back_to_built_in_text() -> None:
    PageText.objects.filter(key="prayer").delete()
    cache.clear()
    assert page_text("prayer").heading == PAGE_TEXT_DEFAULTS["prayer"]["heading"]
    assert page_text("no-such-key").heading == ""


# ------------------------------------------------------------------ page text on the site
def _edit(key: str, **fields: str) -> None:
    obj = PageText.objects.get(key=key)
    for name, value in fields.items():
        setattr(obj, name, value)
    obj.save()  # save() clears the cache, like an admin edit


@pytest.mark.parametrize(
    ("key", "url"),
    [
        ("events", "/events/"),
        ("prayer", "/prayer/"),
        ("about", "/about/"),
        ("get_involved", "/get-involved/"),
        ("resources", "/resources/"),
        ("contact", "/contact/"),
        ("newsletter", "/newsletter/subscribe/"),
    ],
)
def test_page_headings_come_from_the_admin(client: Client, key: str, url: str) -> None:
    _edit(key, eyebrow="Edited eyebrow", heading="Edited heading for test", intro="Edited intro text")
    html = client.get(url).content.decode()
    assert "Edited heading for test" in html and "Edited eyebrow" in html and "Edited intro text" in html


def test_home_hero_sections_cards_cta_and_footer_are_editable(client: Client) -> None:
    from core.models import HeroSlide

    HeroSlide.objects.update(is_active=False)  # the "home_hero" text is the fallback when no slide is live
    _edit("home_hero", heading="Hope Restored.", highlight="Generations Rising.", intro="Hero intro")
    _edit("home_card_prayer", heading="Pray with us", intro="Card text")
    _edit("cta_band", heading="Join the rebuilding", intro="CTA text")
    _edit("footer_newsletter", heading="Keep in touch", intro="Footer text")
    html = client.get("/").content.decode()
    for text in (
        "Hope Restored.",
        "Generations Rising.",
        "Hero intro",
        "Pray with us",
        "Join the rebuilding",
        "Keep in touch",
    ):
        assert text in html
    assert '<span class="text-flame-gradient">Reviving Generations.</span>' not in html  # hero replaced


def test_seo_title_and_description_override(client: Client) -> None:
    _edit("events", seo_title="Christian events in Juba", seo_description="Custom search summary")
    html = client.get("/events/").content.decode()
    assert "<title>Christian events in Juba</title>" in html
    assert 'name="description" content="Custom search summary"' in html


def test_page_text_is_escaped(client: Client) -> None:
    _edit("events", heading='<script>alert("x")</script>', intro="<b>bold</b>")
    html = client.get("/events/").content.decode()
    assert '<script>alert("x")</script>' not in html
    assert "&lt;script&gt;" in html and "&lt;b&gt;bold&lt;/b&gt;" in html


def test_giving_settings_intro_still_wins_over_page_text(client: Client) -> None:
    from giving.models import GivingSettings

    gs = GivingSettings.load()
    gs.give_intro = "Intro from giving settings"
    gs.save()
    _edit("give", intro="Intro from page text")
    html = client.get("/give/").content.decode()
    assert "Intro from giving settings" in html and "Intro from page text" not in html


# ------------------------------------------------------------------ form options
def test_new_option_appears_in_form_and_is_accepted(client: Client) -> None:
    FormOption.objects.create(list="volunteer_interest", value="prison", label="Prison ministry", order=1)
    assert "Prison ministry" in client.get("/get-involved/").content.decode()
    data = {
        "full_name": "Test Volunteer",
        "email": "vol@example.test",
        "phone": "+211 900 000 000",
        "country": "South Sudan",
        "location": "Juba",
        "interests": ["prison"],
        "availability": "weekends",
        "consent": "on",
    }
    assert client.post("/get-involved/", data).status_code == 302
    application = VolunteerApplication.objects.get()
    assert application.interest_labels == ["Prison ministry"]
    assert application.get_availability_display() == "Weekends"


def test_switched_off_option_is_hidden_and_rejected_but_keeps_its_label(client: Client) -> None:
    option = FormOption.objects.get(list="contact_topic", value="media")
    option.is_active = False
    option.save()
    assert ("media", "Media & invitations") not in option_choices("contact_topic")
    assert "Media &amp; invitations" not in client.get("/contact/").content.decode()
    data = {
        "name": "A",
        "email": "a@example.test",
        "topic": "media",
        "subject": "S",
        "message": "M",
        "consent": "on",
    }
    assert client.post("/contact/", data).status_code == 200  # form error, not saved
    assert not ContactMessage.objects.exists()
    assert option_label("contact_topic", "media") == "Media & invitations"  # old messages still readable


def test_renamed_label_shows_everywhere() -> None:
    message = ContactMessage.objects.create(
        name="A", email="a@example.test", subject="S", message="M", topic="events", consent=True
    )
    option = FormOption.objects.get(list="contact_topic", value="events")
    option.label = "Conferences & events"
    option.save()
    assert message.get_topic_display() == "Conferences & events"


def test_last_active_option_cannot_be_switched_off() -> None:
    FormOption.objects.filter(list="partner_type").exclude(value="church").update(is_active=False)
    last = FormOption.objects.get(list="partner_type", value="church")
    last.is_active = False
    with pytest.raises(ValidationError, match="must stay active"):
        last.full_clean()


def test_unknown_value_falls_back_to_raw_value() -> None:
    assert option_label("contact_topic", "legacy-topic") == "legacy-topic"
    assert option_label("contact_topic", "") == ""


# ------------------------------------------------------------------ admin access
def test_media_edits_page_text_but_cannot_add_or_delete(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEDIA))
    obj = PageText.objects.get(key="events")
    url = f"{admin_prefix}core/pagetext/{obj.pk}/change/"
    resp = client.post(
        url,
        {
            "eyebrow": "E",
            "heading": "Changed by media",
            "highlight": "",
            "intro": "",
            "seo_title": "",
            "seo_description": "",
        },
    )
    assert resp.status_code == 302
    obj.refresh_from_db()
    assert obj.heading == "Changed by media" and obj.key == "events"
    assert client.get(f"{admin_prefix}core/pagetext/add/").status_code == 403
    assert client.get(f"{admin_prefix}core/pagetext/{obj.pk}/delete/").status_code == 403


def test_secretary_manages_form_options_but_cannot_change_codes(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(SECRETARY))
    resp = client.post(
        f"{admin_prefix}core/formoption/add/",
        {
            "list": "volunteer_interest",
            "label": "Hospital visits",
            "value": "hospital",
            "order": 5,
            "is_active": "on",
        },
    )
    assert resp.status_code == 302
    option = FormOption.objects.get(value="hospital")
    client.post(
        f"{admin_prefix}core/formoption/{option.pk}/change/",
        {
            "list": "contact_topic",
            "label": "Hospital ministry",
            "value": "changed",
            "order": 5,
            "is_active": "on",
        },
    )
    option.refresh_from_db()
    assert (option.label, option.value, option.list) == (
        "Hospital ministry",
        "hospital",
        "volunteer_interest",
    )
    assert client.get(f"{admin_prefix}core/formoption/{option.pk}/delete/").status_code == 403


@pytest.mark.parametrize("role", [PROGRAMS])
def test_other_roles_cannot_edit_site_text(make_staff, verified_client, admin_prefix, role) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(role))
    obj = PageText.objects.get(key="events")
    assert client.get(f"{admin_prefix}core/pagetext/{obj.pk}/change/").status_code == 403
    assert client.get(f"{admin_prefix}core/formoption/").status_code == 403


def test_admin_submission_forms_use_option_dropdowns(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    message = ContactMessage.objects.create(
        name="A", email="a@example.test", subject="S", message="M", topic="events", consent=True
    )
    client = verified_client(make_staff(SECRETARY))
    html = client.get(f"{admin_prefix}contact/contactmessage/{message.pk}/change/").content.decode()
    assert '<select name="topic"' in html and "General enquiry" in html
    listing = client.get(f"{admin_prefix}contact/contactmessage/").content.decode()
    assert "Events" in listing  # label, not the raw code, in the list and filter


# ------------------------------------------------------------------ logos, wordmark, extra pages
def _png() -> SimpleUploadedFile:
    import io

    from PIL import Image

    buf = io.BytesIO()
    Image.new("RGBA", (300, 120), (240, 101, 42, 255)).save(buf, format="PNG")
    return SimpleUploadedFile("logo.png", buf.getvalue(), content_type="image/png")


def test_uploaded_logos_replace_built_in_ones(client: Client, settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from core.models import SiteSettings

    settings.MEDIA_ROOT = tmp_path
    site = SiteSettings.load()
    site.logo = _png()
    site.logo_on_dark = _png()
    site.save()
    html = client.get("/").content.decode()
    assert f"{site.logo.name.rsplit('.', 1)[0]}_w480.webp" in html  # header
    assert f"{site.logo_on_dark.name.rsplit('.', 1)[0]}_w480.webp" in html  # footer
    assert f"{site.logo_on_dark.name.rsplit('.', 1)[0]}_w960.webp" in html  # hero + link preview
    assert "brand/mark-light-128" not in html


def test_header_wordmark_follows_ministry_name(client: Client) -> None:
    from core.models import SiteSettings

    site = SiteSettings.load()
    site.ministry_name = "Restoration Fellowship Church"
    site.save()
    html = client.get("/contact/").content.decode()
    assert "Restoration Fellowship" in html and ">Church</span>" in html
    assert "REBUILDING LIVES" not in html


def test_extra_pages_can_be_listed_in_the_footer(client: Client) -> None:
    from core.models import Page

    page = Page.objects.create(
        title="Statement of faith", slug="statement-of-faith", body="We believe...", is_published=True
    )
    assert "Statement of faith" not in client.get("/").content.decode()
    page.show_in_footer = True
    page.save()
    html = client.get("/").content.decode()
    assert 'href="/pages/statement-of-faith/"' in html
    page.is_published = False
    page.save()
    assert "Statement of faith" not in client.get("/").content.decode()
    assert client.get("/pages/statement-of-faith/").status_code == 404
