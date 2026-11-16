"""Create the staff role groups with least-privilege permissions (idempotent).

Permissions are normally created after migrations (post_migrate), so they are created here first.
To change a role later, edit accounts/roles.py and run:  python manage.py sync_roles
"""

from django.db import migrations


def create_roles(apps, schema_editor):  # type: ignore[no-untyped-def]
    from django.contrib.auth.management import create_permissions

    from accounts.roles import sync_roles

    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, apps=apps, verbosity=0)
        app_config.models_module = None
    sync_roles(apps, strict=False)  # later models get their permissions in later migrations


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("audit", "0002_append_only_trigger"),
        ("branches", "0001_initial"),
        ("contact", "0001_initial"),
        ("core", "0001_initial"),
        ("events", "0001_initial"),
        ("giving", "0001_initial"),
        ("leadership", "0001_initial"),
        ("media_library", "0001_initial"),
        ("news", "0001_initial"),
        ("newsletter", "0001_initial"),
        ("prayer", "0001_initial"),
        ("programs", "0001_initial"),
        ("registrations", "0001_initial"),
        ("resources", "0001_initial"),
        ("otp_totp", "0003_add_timestamps"),
        ("otp_static", "0003_add_timestamps"),
    ]

    operations = [migrations.RunPython(create_roles, migrations.RunPython.noop)]
