"""Existing slides keep their look; the home hero becomes editable (live + draft rows)."""

from django.db import migrations

DEFAULT_TITLE = "Rebuilding Lives. Reviving Generations."


def forward(apps, schema_editor):  # type: ignore[no-untyped-def]
    HeroSlide = apps.get_model("core", "HeroSlide")
    HeroSettings = apps.get_model("core", "HeroSettings")
    PageText = apps.get_model("core", "PageText")
    # A slide that had a photo was a photo slide; the others used the dark flame background (theme colour).
    HeroSlide.objects.exclude(image="").update(background_type="photo")

    # The static hero used the "home_hero" page text and fixed Give / Volunteer buttons.
    text = PageText.objects.filter(key="home_hero").first()
    title = (" ".join(x for x in (text.heading, text.highlight) if x) if text else "") or DEFAULT_TITLE
    title = title[:120]
    subtitle = (text.intro if text else "")[:300]
    for state in ("live", "draft"):
        HeroSettings.objects.get_or_create(
            state=state,
            defaults={
                "title": title,
                "subtitle": subtitle,
                "background_type": "theme",
                "button_text": "Give",
                "button_link": "/give/",
                "button2_text": "Volunteer",
                "button2_link": "/get-involved/",
                "show_scripture": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0016_hero_backgrounds")]
    operations = [migrations.RunPython(forward, migrations.RunPython.noop)]
