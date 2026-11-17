"""Give Media & Communications (and the Founder) their permissions on Hero slides and Partners."""

from django.db import migrations


def resync_roles(apps, schema_editor):  # type: ignore[no-untyped-def]
    from django.contrib.auth.management import create_permissions

    from accounts.roles import sync_roles

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps, strict=False)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0003_roles_site_text"),
        ("core", "0006_heroslide_partner"),
        ("media_library", "0002_testimony_approval_name_display"),
    ]

    operations = [migrations.RunPython(resync_roles, migrations.RunPython.noop)]
