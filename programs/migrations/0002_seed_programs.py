"""Seed the core programmes. Text is a neutral placeholder (the brief was unavailable, see DECISIONS D-001);
edit it in the admin."""

from django.db import migrations

PROGRAMS = [
    (
        "youth-revival-conferences",
        "Youth Revival Conferences",
        "flame",
        "Gatherings that call a generation back to God through worship, the Word and prayer.",
    ),
    (
        "evangelism-and-missions",
        "Evangelism & Missions",
        "globe",
        "Taking the Gospel to communities in South Sudan and beyond through outreach and missions.",
    ),
    (
        "discipleship",
        "Discipleship",
        "book",
        "Helping believers grow in faith through Bible study, mentoring and small groups.",
    ),
    (
        "youth-and-leadership-development",
        "Youth & Leadership Development",
        "star",
        "Equipping young people to lead with character, faith and skill in church and society.",
    ),
    (
        "prayer-and-intercession",
        "Prayer & Intercession",
        "hands",
        "Standing together in prayer for lives, families, communities and the nation.",
    ),
]


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    Program = apps.get_model("programs", "Program")
    for order, (slug, title, icon, summary) in enumerate(PROGRAMS, start=1):
        Program.objects.get_or_create(
            slug=slug,
            defaults={
                "title": title,
                "icon": icon,
                "summary": summary,
                "order": order,
                "is_published": True,
                "is_featured": True,
            },
        )


class Migration(migrations.Migration):
    dependencies = [("programs", "0001_initial")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
