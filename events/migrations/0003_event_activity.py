"""Events now belong to an Activity instead of a programme. Each event keeps its link where a programme maps to
exactly one activity; events of the old "Evangelism & Missions" programme (now three activities) are left
unlinked for staff to assign, and are listed in the migration output."""

import django.db.models.deletion
from django.db import migrations, models

PROGRAMME_TO_ACTIVITY = {
    "youth-revival-conferences": "annual-youth-revival-conference",
    "prayer-and-intercession": "prayer-and-intercession",
    "discipleship": "mentorship-programme",
    "youth-and-leadership-development": "leadership-and-ministerial-trainings",
}


def link_events(apps, schema_editor):  # type: ignore[no-untyped-def]
    Event = apps.get_model("events", "Event")
    Activity = apps.get_model("programs", "Activity")
    activities = {a.slug: a for a in Activity.objects.all()}
    unlinked = []
    for event in Event.objects.exclude(program=None).select_related("program"):
        slug = PROGRAMME_TO_ACTIVITY.get(event.program.slug) or event.program.slug
        activity = activities.get(slug) or activities.get(f"old-{event.program.slug}")
        if activity is None:
            unlinked.append(event.pk)
            continue
        event.activity = activity
        event.save(update_fields=["activity"])
    if unlinked:
        print(f"\n  Events to link to an activity in the admin (ids): {unlinked}")  # noqa: T201


def unlink(apps, schema_editor):  # type: ignore[no-untyped-def]
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("events", "0002_upload_policies"),
        ("programs", "0005_seed_activities"),
    ]

    operations = [
        migrations.AddField(
            model_name="event",
            name="activity",
            field=models.ForeignKey(
                blank=True,
                help_text="The ministry activity this event belongs to (shown on the activity page).",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="events",
                to="programs.activity",
            ),
        ),
        migrations.RunPython(link_events, unlink),
        migrations.RemoveField(model_name="event", name="program"),
    ]
