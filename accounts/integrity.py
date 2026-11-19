"""Periodic integrity check of accounts and roles (catches edits that bypass the ORM, e.g. raw SQL).

The fingerprint is an HMAC (keyed with SECRET_KEY, which is not in the database) over every account's
privileged state, group memberships, group permissions, direct permissions and department memberships.
Sanctioned changes refresh it; the scheduled check compares it with reality and alerts the Super Admins on a
mismatch, then re-baselines so each unexplained change is reported once.
"""

from __future__ import annotations

import json

from django.db import transaction
from django.utils import timezone
from django.utils.crypto import salted_hmac

SALT = "rlm.accounts.integrity.v1"


def compute_fingerprint() -> str:
    from django.contrib.auth.models import Group

    from portal.models import DepartmentMembership

    from .models import User

    users = list(
        User._base_manager.order_by("pk").values_list(
            "pk", "email", "password", "is_active", "is_staff", "is_superuser", "branch_id", "deleted_at"
        )
    )
    groups = list(
        User.groups.through.objects.order_by("user_id", "group_id").values_list("user_id", "group_id")
    )
    perms = list(
        User.user_permissions.through.objects.order_by("user_id", "permission_id").values_list(
            "user_id", "permission_id"
        )
    )
    group_perms = list(
        Group.permissions.through.objects.order_by("group_id", "permission_id").values_list(
            "group_id", "permission_id"
        )
    )
    memberships = list(
        DepartmentMembership.objects.order_by("user_id", "department_id").values_list(
            "user_id", "department_id", "is_head"
        )
    )
    payload = json.dumps([users, groups, perms, group_perms, memberships], default=str, separators=(",", ":"))
    return salted_hmac(SALT, payload, algorithm="sha256").hexdigest()


def _state():  # type: ignore[no-untyped-def]
    from .models import AccountIntegrityState

    state = AccountIntegrityState.objects.order_by("pk").first()
    return state or AccountIntegrityState.objects.create()


def store_fingerprint() -> None:
    state = _state()
    state.fingerprint = compute_fingerprint()
    state.last_checked_at = timezone.now()
    state.save()


def refresh_fingerprint_on_commit() -> None:
    transaction.on_commit(store_fingerprint)


def check_integrity() -> bool:
    """Return True when nothing changed outside the approved paths. Alerts and re-baselines otherwise."""
    from audit.models import AuditLog
    from audit.services import log_event

    from .guard import alert_super_admins

    state = _state()
    current = compute_fingerprint()
    ok = not state.fingerprint or state.fingerprint == current
    if not ok:
        log_event(
            AuditLog.Action.ACCOUNT_INTEGRITY, actor_email="system:integrity-check", extra={"mismatch": True}
        )
        alert_super_admins(
            "The scheduled integrity check found account or role data that changed outside the staff portal."
        )
    state.fingerprint = current
    state.last_checked_at = timezone.now()
    state.save()
    return ok
