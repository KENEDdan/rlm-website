"""Seed the Founder (confirmed, published) and the other offices as unpublished placeholders.

Only the Founder's name is known. Every other office is "To be confirmed by leadership" and stays hidden
until an admin enters the confirmed name, sets status "Confirmed" and ticks "published".
"""

from django.db import migrations

TBC = "To be confirmed by leadership"

DEPARTMENTS = [
    ("administration", "Administration", 1),
    ("finance", "Finance & Administration", 2),
    ("programs-events", "Programs & Events", 3),
    ("media-communications", "Media & Communications", 4),
    ("youth", "Youth Ministry", 5),
    ("evangelism-missions", "Evangelism & Missions", 6),
]

OFFICES = [
    ("Secretary", "administration", 10),
    ("Finance & Administration", "finance", 20),
    ("Programs & Events Coordinator", "programs-events", 30),
    ("Media & Communications Lead", "media-communications", 40),
    ("Youth Ministry Head", "youth", 50),
    ("Evangelism & Missions Head", "evangelism-missions", 60),
]


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    Department = apps.get_model("leadership", "Department")
    Leader = apps.get_model("leadership", "Leader")
    depts = {}
    for slug, name, order in DEPARTMENTS:
        depts[slug], _ = Department.objects.get_or_create(slug=slug, defaults={"name": name, "order": order})

    Leader.objects.get_or_create(
        name="Justine Malish Michael",
        defaults={
            "role_title": "Founder",
            "order": 0,
            "confirmation_status": "confirmed",
            "is_published": True,
            "bio": "",
        },
    )
    for title, dept, order in OFFICES:
        Leader.objects.get_or_create(
            role_title=title,
            name=TBC,
            defaults={
                "department": depts[dept],
                "order": order,
                "confirmation_status": "tbc",
                "is_published": False,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("leadership", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
