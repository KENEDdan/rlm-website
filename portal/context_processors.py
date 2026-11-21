"""Sidebar for portal pages: only the departments and screens this user may open."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django.urls import reverse
from django.utils.functional import SimpleLazyObject

from .access import MEMBER, get_access, is_verified_staff


def _nav(request: HttpRequest) -> dict[str, Any]:
    from .models import Department
    from .resources import resources_for

    access = get_access(request)
    names = dict(Department.objects.values_list("code", "name"))
    departments = []
    for code in access.departments():
        groups: dict[str, list[dict[str, str]]] = {}
        for resource in resources_for(code):
            if resource.nav and resource.can(access, "view"):
                groups.setdefault(resource.nav_group or "Records", []).append(
                    {"label": resource.label, "url": resource.url("list"), "icon": resource.icon}
                )
        departments.append(
            {
                "code": code,
                "name": names.get(code, code.title()),
                "url": reverse("portal:dashboard", args=[code]),
                "level": access.level(code),
                "is_head": access.is_head(code),
                "groups": groups,
                "budget_url": (
                    reverse("portal:finance:department_budget", args=[code])
                    if access.level(code) >= MEMBER and code != "finance"
                    else ""
                ),
            }
        )
    from core import vision_mission
    from finance.approvals import is_approver, pending_items
    from finance.executive import can_view as executive_can_view
    from giving import bank_details

    approver = is_approver(request.user)
    vm_approver = vision_mission.is_approver(request.user)
    return {
        "show_website": access.is_technical,
        "show_bank_details": bank_details.can_view(request.user),
        "bank_pending": bank_details.pending() is not None if bank_details.can_view(request.user) else False,
        "show_vm_approvals": vm_approver and not access.is_technical,
        "vm_pending": vision_mission.open_changes().filter(status="submitted").count() if vm_approver else 0,
        "approvals_url": reverse("portal:finance:approvals") if (approver or access.is_super_admin) else "",
        "approvals_pending": len(pending_items()) if approver else 0,
        "access": access,
        "departments": departments,
        "show_executive": access.is_executive,
        "show_targets": access.is_executive or access.is_super_admin or bool(access.member_departments()),
        "show_executive_finance": executive_can_view(access),
        "show_accounts": access.is_super_admin,
        "show_admin": request.user.is_superuser or bool(request.user.get_all_permissions()),
        "admin_url": "/" + settings.ADMIN_URL,
    }


def portal(request: HttpRequest) -> dict[str, Any]:
    prefix = "/" + settings.PORTAL_URL
    if not request.path.startswith(prefix) or not is_verified_staff(request):
        return {}
    return {"portal_nav": SimpleLazyObject(lambda: _nav(request)), "portal_prefix": prefix}
