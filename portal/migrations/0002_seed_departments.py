"""Create the seven departments and move existing role holders into them.

Old role -> department: Secretary -> Membership Administration, Finance & Admin -> Finance & Resource
Mobilization, Programs & Events -> Missions & Outreach, Media & Communications -> itself (as members, not
heads: the Super Admin marks heads in the portal). The retired "Departmental Heads" group is removed; its
holders keep their other roles and must be given a department by the Super Admin (docs/DECISIONS.md D-016).
"""

from django.db import migrations

DEPARTMENTS = [
    (
        "membership",
        "Membership Administration",
        "Managing membership records, recruitment, communication, and general administrative coordination "
        "of ministry members and volunteers.",
    ),
    (
        "finance",
        "Finance & Resource Mobilization",
        "Financial management, accountability, fundraising, donor relations and resource mobilization for "
        "the ministry's financial sustainability.",
    ),
    (
        "logistics",
        "Logistics & Procurement",
        "Making sure the ministry has the materials, equipment, transport, supplies and logistical "
        "arrangements it needs for its activities.",
    ),
    (
        "media",
        "Media & Communications",
        "The ministry's public image, digital communication, media production, documentation and visibility.",
    ),
    (
        "missions",
        "Missions & Outreach",
        "Evangelism, missionary activities, community engagement and taking the Gospel to unreached "
        "communities.",
    ),
    (
        "discipleship",
        "Discipleship",
        "Nurturing spiritual growth, biblical understanding, Christian maturity and leadership development "
        "among new converts, believers and members.",
    ),
    (
        "development",
        "Development & Infrastructure",
        "Physical development, infrastructure, facilities, long-term institutional growth and sustainability.",
    ),
]

GROUP_TO_CODE = {
    "Secretary": "membership",
    "Membership Administration": "membership",
    "Finance & Admin": "finance",
    "Finance & Resource Mobilization": "finance",
    "Programs & Events": "missions",
    "Missions & Outreach": "missions",
    "Media & Communications": "media",
}


def seed(apps, schema_editor):  # type: ignore[no-untyped-def]
    Department = apps.get_model("portal", "Department")
    Membership = apps.get_model("portal", "DepartmentMembership")
    Group = apps.get_model("auth", "Group")
    for order, (code, name, purpose) in enumerate(DEPARTMENTS, start=1):
        Department.objects.update_or_create(code=code, defaults={"name": name, "purpose": purpose, "order": order})
    for group in Group.objects.filter(name__in=GROUP_TO_CODE):
        department = Department.objects.get(code=GROUP_TO_CODE[group.name])
        for user in group.user_set.all():
            Membership.objects.get_or_create(user=user, department=department)
    Group.objects.filter(name="Departmental Heads").delete()


class Migration(migrations.Migration):
    dependencies = [
        ("portal", "0001_initial"),
        ("accounts", "0005_portal_accounts"),
    ]

    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
