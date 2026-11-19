from typing import Any

from django.contrib.auth.models import Group
from django.contrib.auth.signals import user_login_failed
from django.db.models.signals import m2m_changed, post_migrate, post_save
from django.dispatch import receiver

from audit.models import AuditLog
from audit.services import log_event

from .guard import record_change, sanctioned
from .models import User


@receiver(user_login_failed)
def _login_failed(sender: Any, credentials: dict[str, Any], request: Any = None, **kwargs: Any) -> None:
    attempted = str(credentials.get("username", ""))[:254]
    log_event(AuditLog.Action.LOGIN_FAILED, request=request, actor_email=attempted)


@receiver(post_save, sender=User, dispatch_uid="accounts.user_changed")
def _user_saved(sender: Any, instance: User, created: bool, raw: bool = False, **kwargs: Any) -> None:
    if raw:
        return
    changes = getattr(instance, "_account_changes", None) or {}
    instance._account_changes = {}
    record_change(instance, changes, kind="user")


def _m2m_names(model: Any, pks: Any) -> list[str]:
    if not pks:
        return []
    if model is Group:
        return sorted(Group.objects.filter(pk__in=pks).values_list("name", flat=True))
    return sorted(f"{p.content_type.app_label}.{p.codename}" for p in model.objects.filter(pk__in=pks))


def _m2m_changed(field: str):  # type: ignore[no-untyped-def]
    def handler(
        sender: Any, instance: Any, action: str, reverse: bool, model: Any, pk_set: Any, **kw: Any
    ) -> None:
        if action not in ("post_add", "post_remove", "pre_clear"):
            return
        if reverse:
            # e.g. group.user_set.add(user) or group.permissions changes: one entry per affected user.
            users = User._base_manager.filter(pk__in=pk_set or []) if model is User else []
            for user in users:
                record_change(user, {field: {action.replace("post_", ""): [str(instance)]}}, kind=field)
            return
        if action == "pre_clear":
            pk_set = set(getattr(instance, field).values_list("pk", flat=True))
        names = _m2m_names(model, pk_set)
        if names:
            verb = {"post_add": "added", "post_remove": "removed", "pre_clear": "removed"}[action]
            record_change(instance, {field: {verb: names}}, kind=field)

    return handler


# weak=False: the handlers are closures; a weak reference would let them be garbage-collected silently.
m2m_changed.connect(
    _m2m_changed("groups"), sender=User.groups.through, weak=False, dispatch_uid="accounts.groups_changed"
)
m2m_changed.connect(
    _m2m_changed("user_permissions"),
    sender=User.user_permissions.through,
    weak=False,
    dispatch_uid="accounts.perms_changed",
)


@receiver(m2m_changed, sender=Group.permissions.through, dispatch_uid="accounts.group_perms_changed")
def _group_permissions_changed(sender: Any, instance: Any, action: str, **kwargs: Any) -> None:
    """Role permissions may only change through ``sync_roles`` (code review + deploy), never ad hoc."""
    from .guard import current_context

    if action in ("post_add", "post_remove", "post_clear") and current_context() is None:
        log_event(
            AuditLog.Action.ACCOUNT_OUT_OF_BAND,
            actor_email="unknown:outside-portal",
            extra={"kind": "group_permissions", "group": str(instance), "action": action},
        )
        from django.db import transaction

        from .guard import alert_super_admins

        transaction.on_commit(lambda: alert_super_admins("Role permissions were changed outside the code."))


def _sync_roles_after_migrate(sender: Any, **kwargs: Any) -> None:
    """Keep the role groups exactly as accounts/roles.py says after every migrate (new models included)."""
    from .roles import sync_roles

    with sanctioned("system:sync_roles"):
        sync_roles(strict=False)


post_migrate.connect(_sync_roles_after_migrate, dispatch_uid="accounts.sync_roles_after_migrate")
