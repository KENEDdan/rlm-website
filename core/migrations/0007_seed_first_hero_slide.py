"""Slide 1 of the home hero: the tagline with Acts 15:16 (editable in the admin under Hero slides)."""

from django.db import migrations

HOME_HERO_LABEL = "Home: hero (only shown when no hero slide is active)"


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    HeroSlide = apps.get_model("core", "HeroSlide")
    SiteSettings = apps.get_model("core", "SiteSettings")
    PageText = apps.get_model("core", "PageText")
    if not HeroSlide.objects.exists():
        site = SiteSettings.objects.filter(pk=1).first()
        HeroSlide.objects.create(
            title=(site.tagline if site and site.tagline else "Rebuilding Lives. Reviving Generations."),
            show_scripture=True,
            button_text="Give",
            button_link="/give/",
            order=0,
            is_active=True,
        )
    PageText.objects.filter(key="home_hero").update(label=HOME_HERO_LABEL)


class Migration(migrations.Migration):
    dependencies = [("core", "0006_heroslide_partner")]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
