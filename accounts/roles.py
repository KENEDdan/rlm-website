"""Single source of truth for staff roles (Django Groups) and their least-privilege permissions.

Letters: v=view a=add c=change d=delete x=export (custom ``export_<model>``) k=confirm donation.
"Own" scoping (Branch Coordinator -> their branch, Departmental Head -> their department) is enforced in the
admin by ``core.admin_mixins.ScopedAdminMixin``. ``sync_roles`` is idempotent: it sets each group's
permissions to exactly this matrix.
"""

from __future__ import annotations

from typing import Any

FOUNDER = "Founder / Super Admin"
SECRETARY = "Secretary"
FINANCE = "Finance & Admin"
PROGRAMS = "Programs & Events"
MEDIA = "Media & Communications"
BRANCH_COORDINATOR = "Branch Coordinator"
DEPARTMENT_HEAD = "Departmental Heads"

ALL_ROLES = [FOUNDER, SECRETARY, FINANCE, PROGRAMS, MEDIA, BRANCH_COORDINATOR, DEPARTMENT_HEAD]
SCOPED_ROLES = {BRANCH_COORDINATOR, DEPARTMENT_HEAD}

MEDIA_MODELS = [
    "media_library.album",
    "media_library.photo",
    "media_library.video",
    "media_library.report",
    "media_library.testimony",
]
RESOURCE_MODELS = ["resources.resourcecategory", "resources.series", "resources.resource"]

ROLE_PERMISSIONS: dict[str, dict[str, str]] = {
    SECRETARY: {
        "branches.country": "v",
        "branches.branch": "v",
        "programs.program": "v",
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
    FINANCE: {
        "giving.givingsettings": "vc",
        "giving.givingcategory": "vacd",
        "giving.currentneed": "vacd",
        "giving.donation": "vcdxk",
        "giving.partnershipenquiry": "vcdx",
        "giving.webhookevent": "v",
    },
    PROGRAMS: {
        "branches.country": "v",
        "branches.branch": "v",
        "programs.program": "vacd",
        "events.event": "vacd",
        "registrations.eventregistration": "vcx",
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
    BRANCH_COORDINATOR: {
        "branches.branch": "vc",
        "programs.program": "v",
        "events.event": "vac",
        "registrations.eventregistration": "vc",
        "registrations.volunteerapplication": "vc",
        "media_library.album": "vac",
        "media_library.photo": "vacd",
        "news.post": "vac",
    },
    DEPARTMENT_HEAD: {
        "branches.branch": "v",
        "programs.program": "vc",
        "events.event": "vac",
        "registrations.eventregistration": "v",
        "news.post": "vac",
    },
}

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


def sync_roles(apps: Any = None, *, strict: bool = True) -> dict[str, int]:
    """Create/refresh every role group. Safe to run any number of times.

    ``strict=False`` skips permissions of models that do not exist yet; the early roles migration uses it,
    because later migrations add models (and their own sync step) after it.
    """
    if apps is None:
        from django.apps import apps as global_apps

        apps = global_apps
    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    summary: dict[str, int] = {}

    founder, _ = Group.objects.get_or_create(name=FOUNDER)
    founder.permissions.set(Permission.objects.all())
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
