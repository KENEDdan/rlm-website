"""Who may see what in the staff portal. Every portal view, list, export and dashboard figure asks this.

Levels per department (higher includes lower):

* ``FOUNDER``  Super Admin: everything, everywhere.
* ``HEAD``     Department head: the whole department, plus approvals, exports and reports.
* ``MEMBER``   Department member: day-to-day records of that department.
* ``BRANCH``   Branch Coordinator: read (and some field entry) in Membership, Missions and Discipleship,
               ONLY for their own branch.

A user may belong to several departments. Branch Coordinators are limited to their branch in every
department they can enter (a coordinator without a branch sees nothing that is tied to a branch).
"""

from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.core.exceptions import PermissionDenied
from django.db.models import QuerySet
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode

from accounts.roles import BRANCH_COORDINATOR, EXECUTIVE

NONE, BRANCH, MEMBER, HEAD, FOUNDER = 0, 1, 2, 3, 4
LEVEL_NAMES = {NONE: "none", BRANCH: "branch", MEMBER: "member", HEAD: "head", FOUNDER: "founder"}

DEPARTMENT_ORDER = ["membership", "finance", "logistics", "media", "missions", "discipleship", "development"]
BRANCH_DEPARTMENTS = {"membership", "missions", "discipleship"}


class Access:
    def __init__(self, user: Any) -> None:
        self.user = user
        authed = bool(getattr(user, "is_authenticated", False))
        self.is_super_admin = authed and bool(getattr(user, "is_super_admin", False))
        groups = set(user.groups.values_list("name", flat=True)) if authed else set()
        self.is_executive = self.is_super_admin or EXECUTIVE in groups
        self.is_branch_coordinator = (not self.is_super_admin) and BRANCH_COORDINATOR in groups
        self.branch_id: int | None = user.branch_id if self.is_branch_coordinator else None
        self.levels: dict[str, int] = {}
        if authed and not self.is_super_admin:
            for code, is_head in user.memberships.values_list("department__code", "is_head"):
                self.levels[code] = HEAD if is_head else MEMBER

    # ------------------------------------------------------------------ department levels
    def level(self, department: str) -> int:
        if self.is_super_admin:
            return FOUNDER
        level = self.levels.get(department, NONE)
        if level == NONE and self.is_branch_coordinator and department in BRANCH_DEPARTMENTS:
            return BRANCH
        return level

    def can_enter(self, department: str) -> bool:
        return self.level(department) >= BRANCH

    def is_head(self, department: str) -> bool:
        return self.level(department) >= HEAD

    def departments(self) -> list[str]:
        return [code for code in DEPARTMENT_ORDER if self.can_enter(code)]

    def member_departments(self) -> list[str]:
        """Departments the user actually belongs to (not via branch coordination)."""
        if self.is_super_admin:
            return list(DEPARTMENT_ORDER)
        return [code for code in DEPARTMENT_ORDER if self.levels.get(code, NONE) >= MEMBER]

    @property
    def has_any_access(self) -> bool:
        return self.is_super_admin or self.is_executive or bool(self.departments())

    # ------------------------------------------------------------------ branch scoping
    @property
    def branch_restricted(self) -> bool:
        return self.is_branch_coordinator

    def restrict_branch(self, qs: QuerySet, lookup: str | None) -> QuerySet:
        if not self.branch_restricted or lookup is None:
            return qs
        if not self.branch_id:
            return qs.none()
        return qs.filter(**{lookup: self.branch_id})

    def allowed_branches(self) -> QuerySet:
        from branches.models import Branch

        qs = Branch.objects.all()
        if self.branch_restricted:
            return qs.filter(pk=self.branch_id) if self.branch_id else qs.none()
        return qs

    # ------------------------------------------------------------------ landing page
    def home_url(self) -> str:
        if self.is_super_admin or self.is_executive:
            return reverse("portal:executive")
        departments = self.member_departments() or self.departments()
        if departments:
            return reverse("portal:dashboard", args=[departments[0]])
        return reverse("portal:no_access")


def get_access(request: HttpRequest) -> Access:
    access = getattr(request, "_portal_access", None)
    if access is None:
        access = Access(request.user)
        request._portal_access = access  # type: ignore[attr-defined]
    return access


def is_verified_staff(request: HttpRequest) -> bool:
    user = request.user
    return bool(
        user.is_authenticated
        and user.is_active
        and user.is_staff
        and getattr(user, "deleted_at", None) is None
        and getattr(user, "is_verified", lambda: False)()
    )


def portal_view(
    department: str | None = None,
    *,
    level: int = MEMBER,
    super_admin: bool = False,
    executive: bool = False,
    url_department: bool = True,
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """Decorator: 2FA-verified staff only, then the department level / Super Admin / executive check.

    ``department=None`` with a ``department`` URL kwarg checks the department named in the URL, unless
    ``url_department=False`` (generic resource screens, where ``Resource.can`` makes the decision because some
    resources are shared with requesting departments).
    """

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not is_verified_staff(request):
                login = reverse("accounts:login")
                return redirect(f"{login}?{urlencode({'next': request.get_full_path()})}")
            access = get_access(request)
            if super_admin and not access.is_super_admin:
                raise PermissionDenied
            if executive and not access.is_executive:
                raise PermissionDenied
            code = department or kwargs.get("department")
            if code is not None:
                if code not in DEPARTMENT_ORDER:
                    raise PermissionDenied
                if (department or url_department) and access.level(code) < level:
                    raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def portal_prefix() -> str:
    return "/" + settings.PORTAL_URL
