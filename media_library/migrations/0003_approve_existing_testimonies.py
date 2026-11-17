"""Testimonies already public (published with consent) stay public under the new approval flag.

Names are NOT carried over as full names: every testimony starts at 'initials only' until staff record
explicit consent for more (privacy by default)."""

from django.db import migrations


def approve(apps, schema_editor):  # type: ignore[no-untyped-def]
    Testimony = apps.get_model("media_library", "Testimony")
    Testimony.objects.filter(is_published=True, consent_confirmed=True).update(is_approved=True)


class Migration(migrations.Migration):
    dependencies = [("media_library", "0002_testimony_approval_name_display")]

    operations = [migrations.RunPython(approve, migrations.RunPython.noop)]
