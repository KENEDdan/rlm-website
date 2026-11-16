"""Seed giving categories and an EMPTY GivingSettings row. No bank details are ever seeded."""

from django.db import migrations

CATEGORIES = [
    ("general-support", "General support"),
    ("youth-revival-conferences", "Youth revival conferences"),
    ("evangelism-and-missions", "Evangelism and missions"),
    ("discipleship", "Discipleship"),
    ("equipment-and-facilities", "Equipment and facilities"),
    ("youth-and-leadership-development", "Youth and leadership development"),
]


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    GivingCategory = apps.get_model("giving", "GivingCategory")
    GivingSettings = apps.get_model("giving", "GivingSettings")
    for order, (slug, name) in enumerate(CATEGORIES, start=1):
        GivingCategory.objects.get_or_create(slug=slug, defaults={"name": name, "order": order})
    GivingSettings.objects.get_or_create(pk=1)


class Migration(migrations.Migration):
    dependencies = [("giving", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
