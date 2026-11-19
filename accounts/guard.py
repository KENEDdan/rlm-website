"""Model-layer guard for accounts and roles.

Every change to a user's privileged state is diffed here and written to the append-only audit log with old
and new values: email, password (as "changed" only), active/staff/superuser flags, branch, soft-delete, groups,
direct permissions and department memberships.

Legitimate changes run inside ``sanctioned(...)``, which ``accounts.services`` opens only after checking that
the actor is an active Super Admin (and the bootstrap command, migrations' role sync and the user's own
password change open it for their narrow purpose). A change made anywhere else - a Django shell, a script,
a future view that forgot to use the services - is still allowed to happen (we cannot stop someone who already
has shell access) but it is logged as ``account_out_of_band`` and every active Super Admin is emailed at once.
``accounts.integrity`` adds a periodic HMAC fingerprint check that also catches raw SQL edits that bypass the
ORM entirely.
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Iterator
from contextvars import ContextVar
from dataclasses import dataclass
from typing import Any

from django.db import transaction
from django.http import HttpRequest

logger = logging.getLogger(__name__)

WATCHED_FIELDS = ("email", "password", "is_active", "is_staff", "is_superuser", "branch_id", "deleted_at")
SECRET_FIELDS = {"password"}


@dataclass(frozen=True)
class ChangeContext:
    reason: str
    actor: Any = None
    request: HttpRequest | None = None


_context: ContextVar[ChangeContext | None] = ContextVar("rlm_account_change_context", default=None)


@contextlib.contextmanager
def sanctioned(reason: str, *, actor: Any = None, request: HttpRequest | None = None) -> Iterator[None]:
    """Mark account/role writes in this block as coming from an authorised code path."""
    token = _context.set(ChangeContext(reason=reason, actor=actor, request=request))
    try:
        yield
    finally:
        _context.reset(token)


def current_context() -> ChangeContext | None:
    return _context.get()


def _display(name: str, value: Any) -> Any:
    if name in SECRET_FIELDS:
        return "(set)" if value else "(empty)"
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return value


def check_user_save(user: Any, update_fields: Any) -> None:
    """Called from ``User.save`` BEFORE writing: compute the diff of watched fields."""
    fields = (
        WATCHED_FIELDS if update_fields is None else [f for f in WATCHED_FIELDS if f in set(update_fields)]
    )
    if not fields:
        user._account_changes = {}
        return
    if user.pk is None:
        user._account_changes = {"created": {"old": None, "new": True}} | {
            f: {"old": None, "new": _display(f, getattr(user, f))}
            for f in fields
            if getattr(user, f) not in (None, "")
        }
        return
    old = type(user)._base_manager.filter(pk=user.pk).values(*fields).first()
    if old is None:
        user._account_changes = {"created": {"old": None, "new": True}}
        return
    changes = {}
    for f in fields:
        before, after = old[f], getattr(user, f)
        if before != after:
            changes[f] = (
                {"old": None, "new": "changed"}
                if f in SECRET_FIELDS
                else {"old": _display(f, before), "new": _display(f, after)}
            )
    user._account_changes = changes


def record_change(target_user: Any, changes: dict[str, Any], *, kind: str) -> None:
    """Write the audit entry; alert Super Admins when the change was not sanctioned."""
    if not changes:
        return
    from audit.models import AuditLog
    from audit.services import log_event

    ctx = current_context()
    extra = {"kind": kind, "changes": changes, "target_user_id": getattr(target_user, "pk", None)}
    if ctx is not None:
        extra["via"] = ctx.reason
        log_event(
            AuditLog.Action.ACCOUNT_CHANGE,
            request=ctx.request,
            user=ctx.actor,
            obj=target_user,
            actor_email="" if ctx.actor is not None else ctx.reason,
            extra=extra,
        )
        from .integrity import refresh_fingerprint_on_commit

        refresh_fingerprint_on_commit()
        return
    log_event(
        AuditLog.Action.ACCOUNT_OUT_OF_BAND,
        obj=target_user,
        actor_email="unknown:outside-portal",
        extra=extra,
    )
    logger.warning("Account change outside the staff portal (user id %s).", getattr(target_user, "pk", None))
    transaction.on_commit(
        lambda: alert_super_admins("An account or role was changed outside the staff portal.")
    )


def alert_super_admins(summary: str) -> int:
    """Email every active Super Admin. The email names no person and carries no personal data."""
    from django.conf import settings
    from django.core.mail import send_mail
    from django.template.loader import render_to_string

    from .models import User

    recipients = list(
        User.objects.filter(is_superuser=True, is_active=True, deleted_at__isnull=True).values_list(
            "email", flat=True
        )
    )
    if not recipients:
        return 0
    body = render_to_string(
        "emails/account_integrity_alert.txt", {"summary": summary, "site_url": settings.SITE_URL}
    )
    try:
        send_mail(
            subject="Security alert: account change outside the staff portal",
            message=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=recipients,
        )
    except OSError:  # pragma: no cover - mail server down; the audit entry is the durable record
        logger.exception("Could not send the account integrity alert.")
        return 0
    return len(recipients)
