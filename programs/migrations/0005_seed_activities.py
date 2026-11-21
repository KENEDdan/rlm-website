"""Seed the four activity categories and thirteen activities (names exactly as given by the ministry, Nov 2026),
route each to its staff department, and carry over any programme text staff had written.

Department routing (defaults; the ministry must confirm, docs/DECISIONS.md D-035):
Charitable and Humanitarian Services -> Development & Infrastructure; Evangelism and Missions -> Missions &
Outreach; Discipleship -> Discipleship; Revival Programme -> Missions & Outreach.

Summaries are short neutral descriptions for the Technical Team to replace with the ministry's own wording.
"""

from django.db import migrations
from django.utils.text import slugify

CATEGORIES = [
    (
        "Charitable and Humanitarian Services",
        "development",
        "heart",
        "Practical care for children, women, families and communities.",
        [
            ("Children, Women, and Family Programme", "Care and support for children, women and families."),
            ("Peace Building Initiative", "Bringing people and communities together in reconciliation and peace."),
            ("Livelihood Skills Development", "Practical skills that help people provide for themselves and their families."),
        ],
    ),
    (
        "Evangelism and Missions",
        "missions",
        "globe",
        "Taking the Gospel of Jesus Christ to schools, prisons, hospitals and communities.",
        [
            ("School Outreach Programme", "Sharing the Gospel and encouragement with students in schools."),
            ("Prison, Hospital and Community Visitations", "Visiting, praying with and serving people where they are."),
            ("Open-Air Crusades", "Public Gospel meetings open to everyone in the community."),
        ],
    ),
    (
        "Discipleship",
        "discipleship",
        "book",
        "Helping believers grow in faith, character and service.",
        [
            ("Mentorship Programme", "Walking alongside young believers as they grow in faith."),
            ("Leadership and Ministerial Trainings", "Equipping godly leaders for the church and society."),
            ("Internship Discipleship Course", "A structured course combining teaching and practical ministry."),
        ],
    ),
    (
        "Revival Programme",
        "missions",
        "flame",
        "Gatherings that call a generation back to God through worship, the Word and prayer.",
        [
            ("Annual Youth Revival Conference", "Our yearly conference of worship, teaching and prayer for young people."),
            ("Monthly Youth Revival Fellowship", "A monthly gathering of young people for worship, the Word and fellowship."),
            ("Prayer and Intercession", "Standing together in prayer for lives, families, communities and the nation."),
            ("Seminars", "Teaching seminars on faith, purpose and Christian living."),
        ],
    ),
]

# Old programme -> the activity that replaced it (its staff-written text and image carry over).
PROGRAMME_TO_ACTIVITY = {
    "youth-revival-conferences": "annual-youth-revival-conference",
    "prayer-and-intercession": "prayer-and-intercession",
    "discipleship": "mentorship-programme",
    "youth-and-leadership-development": "leadership-and-ministerial-trainings",
    "evangelism-and-missions": None,  # covers three activities: text stays with the category instead
}
SEEDED_PROGRAMMES = {
    "youth-revival-conferences",
    "evangelism-and-missions",
    "discipleship",
    "youth-and-leadership-development",
    "prayer-and-intercession",
}


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    Category = apps.get_model("programs", "ActivityCategory")
    Activity = apps.get_model("programs", "Activity")
    Program = apps.get_model("programs", "Program")
    Department = apps.get_model("portal", "Department")
    departments = {d.code: d for d in Department.objects.all()}

    for c_order, (title, dept, icon, summary, activities) in enumerate(CATEGORIES, start=1):
        category, _ = Category.objects.get_or_create(
            slug=slugify(title),
            defaults={
                "title": title,
                "summary": summary,
                "icon": icon,
                "order": c_order,
                "department": departments.get(dept),
                "is_published": True,
            },
        )
        for a_order, (a_title, a_summary) in enumerate(activities, start=1):
            Activity.objects.get_or_create(
                slug=slugify(a_title),
                defaults={
                    "category": category,
                    "title": a_title,
                    "summary": a_summary,
                    "icon": icon,
                    "order": a_order,
                    "department": departments.get(dept),
                    "is_published": True,
                    "is_featured": True,
                },
            )

    # Carry over programme content staff wrote themselves (body, image, SEO), never the placeholder seed text.
    evangelism = Category.objects.get(slug="evangelism-and-missions")
    revival = Category.objects.get(slug="revival-programme")
    for program in Program.objects.all():
        target_slug = PROGRAMME_TO_ACTIVITY.get(program.slug, "")
        if program.slug in SEEDED_PROGRAMMES:
            target = Activity.objects.filter(slug=target_slug).first() if target_slug else None
            if target is not None:
                changed = False
                for field in ("body", "image", "image_alt", "seo_title", "seo_description"):
                    if getattr(program, field) and not getattr(target, field):
                        setattr(target, field, getattr(program, field))
                        changed = True
                if changed:
                    target.save()
            elif program.slug == "evangelism-and-missions" and program.body and not evangelism.body:
                evangelism.body = program.body
                evangelism.save()
            continue
        # A programme the ministry added itself: kept as an UNPUBLISHED activity for the Technical Team to review.
        slug = program.slug if not Activity.objects.filter(slug=program.slug).exists() else f"old-{program.slug}"[:140]
        Activity.objects.create(
            category=revival,
            slug=slug,
            title=program.title,
            summary=program.summary,
            body=program.body,
            icon=program.icon,
            image=program.image,
            image_alt=program.image_alt,
            seo_title=program.seo_title,
            seo_description=program.seo_description,
            order=100 + program.order,
            is_published=False,
            is_featured=False,
        )


def unseed(apps, schema_editor):  # type: ignore[no-untyped-def]
    apps.get_model("programs", "Activity").objects.all().delete()
    apps.get_model("programs", "ActivityCategory").objects.all().delete()


class Migration(migrations.Migration):
    dependencies = [
        ("programs", "0004_activities"),
        ("portal", "0002_seed_departments"),
    ]
    operations = [migrations.RunPython(seed, unseed)]
