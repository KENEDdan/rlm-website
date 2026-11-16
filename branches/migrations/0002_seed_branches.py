"""Seed South Sudan with the Juba and Yei branches. NO contact details (entered later in the admin)."""

from django.db import migrations

BRANCHES = [
    {
        "slug": "juba",
        "name": "Juba",
        "city": "Juba",
        "order": 1,
        "summary": "Our branch in Juba, the capital of South Sudan.",
    },
    {
        "slug": "yei",
        "name": "Yei",
        "city": "Yei",
        "order": 2,
        "summary": "Our branch in Yei, Central Equatoria.",
    },
]


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    Country = apps.get_model("branches", "Country")
    Branch = apps.get_model("branches", "Branch")
    country, _ = Country.objects.get_or_create(code="SS", defaults={"name": "South Sudan", "order": 1})
    for data in BRANCHES:
        Branch.objects.get_or_create(
            slug=data["slug"],
            defaults={**data, "country": country, "is_published": True},
        )


class Migration(migrations.Migration):
    dependencies = [("branches", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
