"""Single source of truth for staff roles (Django Groups) and their least-privilege WEBSITE permissions.

There are seven ministry departments (docs/responsibilities.md). Each has a Django Group of the same name
that grants the Django-admin permissions its people need for PUBLIC WEBSITE content (news, events, gallery…).
Department membership itself lives in ``portal.DepartmentMembership`` (user, department, is_head); the
group is derived from it by ``accounts.services`` so the two can never disagree. The operational records
(members, ledger, procurement…) are NOT in the Django admin for staff: they live in the staff portal, where
``portal.access`` scopes every view, export and number by department, head flag and branch.

Letters: v=view a=add c=change d=delete x=export (custom ``export_<model>``) k=confirm donation.
``sync_roles`` is idempotent: it sets each group's permissions to exactly this matrix.
"""

from __future__ import annotations

from typing import Any

FOUNDER = "Founder / Super Admin"
BRANCH_COORDINATOR = "Branch Coordinator"
EXECUTIVE = "Executive Leadership"
# Website Administration: website content ONLY (docs/DECISIONS.md D-034). No department, no portal records,
# no finance, donors, members, prayer, discipleship or accounts.
TECHNICAL = "Technical Team"

# The seven departments. (code, group name) - the code is used in URLs and in code, the name everywhere else.
MEMBERSHIP = "Membership Administration"
FINANCE = "Finance & Resource Mobilization"
LOGISTICS = "Logistics & Procurement"
MEDIA = "Media & Communications"
MISSIONS = "Missions & Outreach"
DISCIPLESHIP = "Discipleship"
DEVELOPMENT = "Development & Infrastructure"

DEPARTMENTS: list[tuple[str, str]] = [
    ("membership", MEMBERSHIP),
    ("finance", FINANCE),
    ("logistics", LOGISTICS),
    ("media", MEDIA),
    ("missions", MISSIONS),
    ("discipleship", DISCIPLESHIP),
    ("development", DEVELOPMENT),
]
DEPARTMENT_GROUPS = [name for _, name in DEPARTMENTS]
GROUP_FOR_CODE = dict(DEPARTMENTS)

ALL_ROLES = [FOUNDER, *DEPARTMENT_GROUPS, BRANCH_COORDINATOR, EXECUTIVE, TECHNICAL]
SCOPED_ROLES = {BRANCH_COORDINATOR}

# Permissions the Founder group must never carry: account and role administration belongs to the
# superuser flag (Super Admin) alone, so a non-superuser who somehow ends up in the Founder group still
# cannot manage accounts.
ACCOUNT_ADMIN_APPS = {"auth", "accounts", "otp_totp", "otp_static", "axes", "sessions", "contenttypes"}
ACCOUNT_ADMIN_MODELS = {("portal", "department"), ("portal", "departmentmembership")}

MEDIA_MODELS = [
    "media_library.album",
    "media_library.photo",
    "media_library.video",
    "media_library.report",
    "media_library.testimony",
]
RESOURCE_MODELS = ["resources.resourcecategory", "resources.series", "resources.resource"]

ROLE_PERMISSIONS: dict[str, dict[str, str]] = {
    # Was "Secretary": contacts, prayer requests, general volunteers, events and news.
    MEMBERSHIP: {
        "branches.country": "v",
        "branches.branch": "v",
        "programs.activity": "v",
        "leadership.department": "vac",
        "leadership.leader": "vac",
        "events.event": "vacd",
        "registrations.eventregistration": "vcx",
        "registrations.volunteerapplication": "vcdx",
        "prayer.prayerrequest": "vcdx",
        "contact.contactmessage": "vcdx",
        "newsletter.subscriber": "vcx",
        **dict.fromkeys(MEDIA_MODELS, "v"),
        "news.post": "vacd",
        "core.formoption": "vac",
    },
    # Was "Finance & Admin".
    FINANCE: {
        "giving.givingsettings": "vc",
        "giving.givingcategory": "vacd",
        "giving.currentneed": "vacd",
        "giving.donation": "vcdxk",
        "giving.partnershipenquiry": "vcdx",
        "giving.webhookevent": "v",
    },
    LOGISTICS: {
        "branches.branch": "v",
        "events.event": "v",
    },
    MEDIA: {
        "core.sociallink": "vacd",
        "core.heroslide": "vacd",
        "core.partner": "vacd",
        "core.pagetext": "vc",
        "branches.branch": "v",
        "leadership.department": "vac",
        "leadership.leader": "vac",
        **dict.fromkeys(MEDIA_MODELS, "vacd"),
        **dict.fromkeys(RESOURCE_MODELS, "vacd"),
        "news.post": "vacd",
        "newsletter.subscriber": "vx",
    },
    # Was "Programs & Events": events and event registrations (activities are website content: Technical Team).
    MISSIONS: {
        "branches.country": "v",
        "branches.branch": "v",
        "programs.activity": "v",
        "events.event": "vacd",
        "registrations.eventregistration": "vcx",
    },
    DISCIPLESHIP: {
        "programs.activity": "v",
        "events.event": "v",
        **dict.fromkeys(RESOURCE_MODELS, "v"),
    },
    DEVELOPMENT: {
        "branches.branch": "v",
    },
    BRANCH_COORDINATOR: {
        "branches.branch": "vc",
        "programs.activity": "v",
        "events.event": "vac",
        "registrations.eventregistration": "vc",
        "registrations.volunteerapplication": "vc",
        "media_library.album": "vac",
        "media_library.photo": "vacd",
        "news.post": "vac",
    },
    EXECUTIVE: {},
    # Website content only. Activity.department is read-only for them (Super Admin sets the routing), and
    # Vision/Mission go through the approval flow (core.ContentChangeRequest), never a direct edit.
    TECHNICAL: {
        "core.sitecontent": "vc",
        "core.herosettings": "vc",
        "core.heroslide": "vacd",
        "core.sociallink": "vacd",
        "core.page": "vac",
        "core.pagetext": "vc",
        "core.partner": "vacd",
        "core.contentversion": "v",
        "core.contentchangerequest": "vac",
        "programs.activitycategory": "vacd",
        "programs.activity": "vacd",
        "leadership.department": "vac",
        "leadership.leader": "vacd",
        "branches.country": "v",
        "branches.branch": "vc",
        "media_library.album": "vc",
        "events.event": "v",
    },
}
# What the Technical Team may NEVER hold, whatever the matrix above says (tests/test_technical_team.py).
TECHNICAL_FORBIDDEN_APPS = {
    "giving", "finance", "membership", "prayer", "discipleship", "registrations", "contact", "newsletter",
    "accounts", "auth", "otp_totp", "otp_static", "axes", "sessions", "audit", "portal", "logistics", "missions",
    "development", "communications",
}  # fmt: skip
TECHNICAL_FORBIDDEN_MODELS = {
    ("core", "sitesettings"),
    ("core", "uploadlimit"),
    ("core", "formoption"),
}

# Groups renamed when the seven departments replaced the original roles (migration accounts 0005).
RENAMED_ROLES = {
    "Secretary": MEMBERSHIP,
    "Finance & Admin": FINANCE,
    "Programs & Events": MISSIONS,
}
RETIRED_ROLES = ["Departmental Heads"]

LETTER_TO_ACTION = {"v": "view", "a": "add", "c": "change", "d": "delete"}


def codenames_for(model_label: str, letters: str) -> list[tuple[str, str]]:
    """Return [(app_label, codename)] for a model label like 'prayer.prayerrequest'."""
    app_label, model = model_label.split(".")
    result = [(app_label, f"{LETTER_TO_ACTION[ch]}_{model}") for ch in letters if ch in LETTER_TO_ACTION]
    if "x" in letters:
        result.append((app_label, f"export_{model}"))
    if "k" in letters:
        result.append((app_label, f"confirm_{model}"))
    return result


def founder_permissions(Permission: Any) -> Any:
    """Everything except account/role administration (that is the superuser flag's job)."""
    qs = Permission.objects.exclude(content_type__app_label__in=ACCOUNT_ADMIN_APPS)
    for app_label, model in ACCOUNT_ADMIN_MODELS:
        qs = qs.exclude(content_type__app_label=app_label, content_type__model=model)
    return qs


def sync_roles(apps: Any = None, *, strict: bool = True) -> dict[str, int]:
    """Create/refresh every role group. Safe to run any number of times.

    ``strict=False`` skips permissions of models that do not exist yet; early migrations use it,
    because later migrations add models (and their own sync step) after them.
    """
    if apps is None:
        from django.apps import apps as global_apps

        apps = global_apps
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    summary: dict[str, int] = {}

    for old, new in RENAMED_ROLES.items():
        if Group.objects.filter(name=old).exists() and not Group.objects.filter(name=new).exists():
            Group.objects.filter(name=old).update(name=new)

    founder, _ = Group.objects.get_or_create(name=FOUNDER)
    founder.permissions.set(founder_permissions(Permission))
    summary[FOUNDER] = founder.permissions.count()

    for role, matrix in ROLE_PERMISSIONS.items():
        group, _ = Group.objects.get_or_create(name=role)
        wanted = []
        for model_label, letters in matrix.items():
            for app_label, codename in codenames_for(model_label, letters):
                perm = Permission.objects.filter(content_type__app_label=app_label, codename=codename).first()
                if perm is None and not strict:
                    continue
                if perm is None:
                    raise LookupError(f"Permission {app_label}.{codename} does not exist (role {role}).")
                wanted.append(perm)
        group.permissions.set(wanted)
        summary[role] = len(wanted)
    return summary
