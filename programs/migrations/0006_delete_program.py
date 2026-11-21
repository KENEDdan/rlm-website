"""The old programme table goes once events and content have moved to activities (0005, events 0003)."""

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("programs", "0005_seed_activities"),
        ("events", "0003_event_activity"),
    ]

    operations = [migrations.DeleteModel(name="Program")]
