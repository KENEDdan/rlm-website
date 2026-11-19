"""Add the questionnaire's partnership categories (Ministry, Institution) to an existing 'partner_type' list.

New lists ('partner_area', 'partnership_type') are seeded by core.site_text.ensure_defaults after migrate.
Existing options and any label edits made in the admin are never changed.
"""

from django.db import migrations

MISSING = [("ministry", "Ministry", 25), ("institution", "Institution", 45)]


def add_missing(apps, schema_editor):  # type: ignore[no-untyped-def]
    FormOption = apps.get_model("core", "FormOption")
    if not FormOption.objects.filter(list="partner_type").exists():
        return  # empty list: ensure_defaults seeds the full questionnaire list
    for value, label, order in MISSING:
        FormOption.objects.get_or_create(list="partner_type", value=value, defaults={"label": label, "order": order})


class Migration(migrations.Migration):
    dependencies = [("core", "0008_sitesettings_retention_unsuccessful_days_and_more")]
    operations = [migrations.RunPython(add_missing, migrations.RunPython.noop)]
