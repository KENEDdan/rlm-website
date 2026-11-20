"""Account and role management. ONLY an active Super Admin can do any of this.

Every function re-checks the actor itself (``_require_super_admin``) - the views check too, but the rule must
hold even if a future view forgets. Writes happen inside ``guard.sanctioned`` so the model-layer guard logs
them as legitimate (with who, IP, old and new values); anything outside these functions is reported as an
out-of-band change.

Safeguards: nobody edits their own roles; only a Super Admin creates a Super Admin; at most
``SUPER_ADMIN_LIMIT`` active Super Admins; the last active Super Admin can never be demoted, deactivated or
deleted; deactivation and deletion end every session at once; no password is ever emailed or displayed.
"""

from __future__ import annotations

import contextlib
import hashlib
import secrets
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.sessions.models import Session
from django.core.exceptions import PermissionDenied
from django.core.mail import send_mail
from django.db import transaction
from django.http import HttpRequest
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from audit.models import AuditLog
from audit.services import log_event

from . import reauth
from .guard import sanctioned
from .integrity import check_integrity
from .models import Invitation, User
from .roles import BRANCH_COORDINATOR, EXECUTIVE, FOUNDER, GROUP_FOR_CODE
from .twofactor import reset_two_factor


class AccountError(Exception):
    """A rule was broken; the message is safe to show to the Super Admin."""


EXTRA_ROLES = {BRANCH_COORDINATOR, EXECUTIVE}


@dataclass
class RoleSpec:
    # department code -> is_head, or (is_head, branch id) for a single-branch assignment (None = all branches)
    departments: dict[str, Any]
    extra_roles: set[str]  # Branch Coordinator / Executive Leadership
    branch_id: int | None
    super_admin: bool = False


# ------------------------------------------------------------------------------------------- checks
def active_super_admins() -> Any:
    return User.objects.filter(is_superuser=True, is_active=True, deleted_at__isnull=True)


def _require_super_admin(actor: Any) -> None:
    if not (actor is not None and getattr(actor, "is_super_admin", False)):
        raise PermissionDenied("Only the Super Admin can manage accounts.")


def _require_reauth(request: HttpRequest) -> None:
    if not reauth.is_fresh(request):
        raise reauth.ReauthRequired


def _require_not_self(actor: Any, user: User) -> None:
    if actor.pk == user.pk:
        raise AccountError("You cannot change your own account or roles. Ask another Super Admin.")


def _is_last_super_admin(user: User) -> bool:
    return user.is_super_admin and not active_super_admins().exclude(pk=user.pk).exists()


def _check_super_admin_limit(exclude: User | None = None) -> None:
    others = active_super_admins()
    if exclude is not None:
        others = others.exclude(pk=exclude.pk)
    if others.count() >= settings.SUPER_ADMIN_LIMIT:
        raise AccountError(
            f"There are already {settings.SUPER_ADMIN_LIMIT} active Super Admins (the maximum). "
            "Remove the Super Admin role from someone first."
        )


@contextlib.contextmanager
def _authorised(request: HttpRequest, reason: str, *, needs_reauth: bool = True) -> Iterator[Any]:
    actor = request.user
    _require_super_admin(actor)
    if needs_reauth:
        _require_reauth(request)
    # Anything changed outside the portal since the last approved state is reported BEFORE we re-baseline.
    check_integrity()
    with transaction.atomic(), sanctioned(reason, actor=actor, request=request):
        yield actor


# ------------------------------------------------------------------------------------------- roles
def department_roles(spec: RoleSpec) -> dict[str, tuple[bool, int | None]]:
    """Normalise ``spec.departments`` to code -> (is_head, branch id or None)."""
    out = {}
    for code, value in spec.departments.items():
        out[code] = (bool(value[0]), value[1]) if isinstance(value, tuple) else (bool(value), None)
    return out


def _validate_spec(spec: RoleSpec) -> None:
    from branches.models import Branch

    for _is_head, branch_id in department_roles(spec).values():
        if branch_id is not None and not Branch.objects.filter(pk=branch_id).exists():
            raise AccountError("Unknown branch.")
    unknown = set(spec.departments) - set(GROUP_FOR_CODE)
    if unknown:
        raise AccountError("Unknown department.")
    if spec.extra_roles - EXTRA_ROLES:
        raise AccountError("Unknown role.")
    if BRANCH_COORDINATOR in spec.extra_roles and not spec.branch_id:
        raise AccountError("A Branch Coordinator must be linked to a branch.")


def _apply_roles(user: User, spec: RoleSpec) -> None:
    from portal.models import Department, DepartmentMembership

    departments = {d.code: d for d in Department.objects.all()}
    wanted = {code: role for code, role in department_roles(spec).items() if code in departments}
    for membership in DepartmentMembership.objects.filter(user=user).select_related("department"):
        code = membership.department.code
        if code not in wanted:
            membership.delete()
        elif (membership.is_head, membership.branch_id) != wanted[code]:
            membership.is_head, membership.branch_id = wanted[code]
            membership.save()
        wanted.pop(code, None)
    for code, (is_head, branch_id) in wanted.items():
        DepartmentMembership.objects.create(
            user=user, department=departments[code], is_head=is_head, branch_id=branch_id
        )

    group_names = {GROUP_FOR_CODE[c] for c in spec.departments} | set(spec.extra_roles)
    if spec.super_admin:
        group_names.add(FOUNDER)
    target = set(Group.objects.filter(name__in=group_names))
    current = set(user.groups.all())
    if current - target:
        user.groups.remove(*(current - target))
    if target - current:
        user.groups.add(*(target - current))


def current_spec(user: User) -> RoleSpec:
    names = set(user.groups.values_list("name", flat=True))
    return RoleSpec(
        departments={
            m.department.code: (m.is_head, m.branch_id) for m in user.memberships.select_related("department")
        },
        extra_roles=names & EXTRA_ROLES,
        branch_id=user.branch_id,
        super_admin=user.is_superuser,
    )


def change_roles(request: HttpRequest, user: User, spec: RoleSpec) -> None:
    _validate_spec(spec)
    with _authorised(request, "portal:change_roles") as actor:
        _require_not_self(actor, user)
        if user.deleted_at:
            raise AccountError("This account was deleted.")
        if user.is_superuser and not spec.super_admin and _is_last_super_admin(user):
            raise AccountError("This is the last active Super Admin; the role cannot be removed.")
        if spec.super_admin and not user.is_superuser and user.is_active:
            _check_super_admin_limit()
        user.is_superuser = spec.super_admin
        user.is_staff = True
        user.branch_id = spec.branch_id
        user.save()
        _apply_roles(user, spec)


# ------------------------------------------------------------------------------------------- invitations
def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _new_invitation(user: User, kind: str, actor: Any) -> tuple[Invitation, str]:
    Invitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True).update(
        revoked_at=timezone.now()
    )
    token = secrets.token_urlsafe(32)
    invitation = Invitation.objects.create(
        user=user,
        kind=kind,
        token_hash=_token_hash(token),
        created_by=actor,
        expires_at=timezone.now() + timedelta(hours=settings.INVITE_TTL_HOURS),
    )
    return invitation, token


def _send_invitation(invitation: Invitation, token: str) -> None:
    """Call AFTER the transaction that created the invitation has committed."""
    link = settings.SITE_URL + reverse("accounts:accept_invite", args=[token])
    context = {
        "link": link,
        "hours": settings.INVITE_TTL_HOURS,
        "kind": invitation.kind,
        "name": invitation.user.get_short_name(),
    }
    address = invitation.user.email  # only ever the address the Super Admin entered
    send_mail(
        subject=render_to_string("emails/staff_invite_subject.txt", context).strip(),
        message=render_to_string("emails/staff_invite.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[address],
    )


def invite_user(request: HttpRequest, *, email: str, full_name: str, spec: RoleSpec) -> User:
    _validate_spec(spec)
    email = email.strip().lower()
    with _authorised(request, "portal:invite") as actor:
        if User._base_manager.filter(email__iexact=email).exists():
            raise AccountError(
                "An invitation could not be created for this address. If the person already has an account, "
                "find it in the account list."
            )
        if spec.super_admin:
            _check_super_admin_limit()
        user = User(email=email, full_name=full_name.strip(), is_staff=True, is_active=False)
        user.set_unusable_password()
        user.is_superuser = spec.super_admin
        user.branch_id = spec.branch_id
        user.save()
        _apply_roles(user, spec)
        invitation, token = _new_invitation(user, Invitation.Kind.INVITE, actor)
        log_event(AuditLog.Action.INVITE_SENT, request=request, obj=user, extra={"invitation": invitation.pk})
    _send_invitation(invitation, token)
    return user


def resend_invitation(request: HttpRequest, user: User) -> None:
    with _authorised(request, "portal:resend_invite") as actor:
        if user.is_active or user.deleted_at or user.has_usable_password():
            raise AccountError("This person has already accepted an invitation.")
        invitation, token = _new_invitation(user, Invitation.Kind.INVITE, actor)
        log_event(AuditLog.Action.INVITE_SENT, request=request, obj=user, extra={"invitation": invitation.pk})
    _send_invitation(invitation, token)


def revoke_invitations(request: HttpRequest, user: User) -> int:
    with _authorised(request, "portal:revoke_invite", needs_reauth=False):
        count = Invitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        log_event(AuditLog.Action.INVITE_REVOKED, request=request, obj=user, extra={"count": count})
    return count


def find_invitation(token: str) -> Invitation | None:
    if not token or len(token) > 100:
        return None
    invitation = Invitation.objects.select_related("user").filter(token_hash=_token_hash(token)).first()
    if invitation is None or not invitation.is_usable or invitation.user.deleted_at is not None:
        return None
    if invitation.kind == Invitation.Kind.RESET and not invitation.user.is_active:
        return None
    return invitation


def accept_invitation(request: HttpRequest, invitation: Invitation, password: str) -> User:
    """The invitee sets their own password. 2FA enrolment is forced right after (accounts.views)."""
    with transaction.atomic():
        locked = Invitation.objects.select_for_update().get(pk=invitation.pk)
        if not locked.is_usable:
            raise AccountError("This link is no longer valid.")
        user = locked.user
        with sanctioned(f"self:accept_{locked.kind}", actor=user, request=request):
            user.set_password(password)
            if locked.kind == Invitation.Kind.INVITE:
                user.is_active = True
                user.deactivated_at = None
            user.save()
        locked.used_at = timezone.now()
        locked.save(update_fields=["used_at"])
        log_event(AuditLog.Action.INVITE_ACCEPTED, request=request, user=user, obj=user)
    return user


# ------------------------------------------------------------------------------------------- lifecycle
def kill_sessions(user: User, request: HttpRequest | None = None) -> int:
    """End every active session of ``user`` (database-backed sessions)."""
    killed = 0
    for session in Session.objects.filter(expire_date__gt=timezone.now()).iterator():
        data = session.get_decoded()
        if str(data.get("_auth_user_id")) == str(user.pk) or str(
            (data.get("2fa_pending") or {}).get("uid")
        ) == str(user.pk):
            session.delete()
            killed += 1
    log_event(AuditLog.Action.SESSIONS_KILLED, request=request, obj=user, extra={"count": killed})
    return killed


def deactivate(request: HttpRequest, user: User) -> None:
    with _authorised(request, "portal:deactivate", needs_reauth=False) as actor:
        _require_not_self(actor, user)
        if _is_last_super_admin(user):
            raise AccountError("This is the last active Super Admin; it cannot be deactivated.")
        user.is_active = False
        user.deactivated_at = timezone.now()
        user.save()
        Invitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
    kill_sessions(user, request)


def reactivate(request: HttpRequest, user: User) -> None:
    with _authorised(request, "portal:reactivate"):
        if user.deleted_at:
            raise AccountError("This account was deleted and cannot be reactivated.")
        if not user.has_usable_password():
            raise AccountError("This person never set a password. Send a new invitation instead.")
        if user.is_superuser:
            _check_super_admin_limit(exclude=user)
        user.is_active = True
        user.deactivated_at = None
        user.dormant_flagged_at = None
        user.save()


def soft_delete(request: HttpRequest, user: User) -> None:
    """Keep the row (audit history points to it) but remove every way in: no password, roles, 2FA or sessions."""
    with _authorised(request, "portal:delete") as actor:
        _require_not_self(actor, user)
        if _is_last_super_admin(user):
            raise AccountError("This is the last active Super Admin; it cannot be deleted.")
        user.is_active = False
        user.is_superuser = False
        user.is_staff = False
        user.deleted_at = timezone.now()
        user.deactivated_at = user.deactivated_at or user.deleted_at
        user.set_unusable_password()
        user.save()
        _apply_roles(user, RoleSpec(departments={}, extra_roles=set(), branch_id=None))
        Invitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True).update(
            revoked_at=timezone.now()
        )
        reset_two_factor(user)
    kill_sessions(user, request)


def reset_2fa(request: HttpRequest, user: User) -> None:
    """Lost phone: remove the authenticator and backup codes; the person enrols again at next sign-in."""
    with _authorised(request, "portal:reset_2fa") as actor:
        _require_not_self(actor, user)
        reset_two_factor(user)
        log_event(AuditLog.Action.TWO_FACTOR_RESET, request=request, obj=user)
    kill_sessions(user, request)


def force_password_reset(request: HttpRequest, user: User) -> None:
    """Invalidate the password now and email a single-use link to choose a new one (no password emailed)."""
    with _authorised(request, "portal:force_password_reset") as actor:
        _require_not_self(actor, user)
        if not user.is_active or user.deleted_at:
            raise AccountError("Reactivate the account first.")
        user.set_unusable_password()
        user.save()
        invitation, token = _new_invitation(user, Invitation.Kind.RESET, actor)
        log_event(AuditLog.Action.INVITE_SENT, request=request, obj=user, extra={"kind": "reset"})
    _send_invitation(invitation, token)
    kill_sessions(user, request)


def unlock(request: HttpRequest, user: User) -> None:
    """Clear a django-axes lockout for this account (after checking it was the real person)."""
    from axes.utils import reset

    with _authorised(request, "portal:unlock", needs_reauth=False):
        reset(username=user.email)
        log_event(AuditLog.Action.ACCOUNT_UNLOCKED, request=request, obj=user)


# ------------------------------------------------------------------------------------------- bootstrap
def bootstrap_super_admin(*, email: str, full_name: str, password: str) -> User:
    """Only path to the FIRST Super Admin (manage.py create_super_admin). Refuses when one exists."""
    with transaction.atomic(), sanctioned("system:create_super_admin"):
        if active_super_admins().exists():
            raise AccountError(
                "A Super Admin already exists. Another one can only be created by an existing Super Admin "
                "in the staff portal (Accounts > Invite)."
            )
        if User._base_manager.filter(email__iexact=email).exists():
            raise AccountError("An account with this email already exists.")
        user = User.objects.create_superuser(email=email, password=password, full_name=full_name)
        user.groups.add(Group.objects.get(name=FOUNDER))
    return user


# ------------------------------------------------------------------------------------------- dormancy
def dormant_sweep(now: Any = None) -> dict[str, int]:
    """Flag accounts unused for DORMANT_FLAG_DAYS; disable after DORMANT_DISABLE_DAYS.

    Super Admins are flagged but never disabled automatically (that could lock the ministry out).
    """
    now = now or timezone.now()
    flag_before = now - timedelta(days=settings.DORMANT_FLAG_DAYS)
    disable_before = now - timedelta(days=settings.DORMANT_DISABLE_DAYS)
    flagged = disabled = 0
    with sanctioned("system:dormant_accounts"):
        for user in User.objects.filter(is_active=True, deleted_at__isnull=True):
            last = user.last_login or user.date_joined
            if last >= flag_before:
                continue
            if last < disable_before and not user.is_superuser:
                user.is_active = False
                user.deactivated_at = now
                user.save()
                kill_sessions(user)
                disabled += 1
            elif user.dormant_flagged_at is None:
                user.dormant_flagged_at = now
                user.save(update_fields=["dormant_flagged_at", "updated_at"])
                flagged += 1
    return {"flagged": flagged, "disabled": disabled}
