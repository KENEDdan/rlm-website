from typing import Any

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from accounts.guard import record_change

from .models import DepartmentMembership


@receiver(post_save, sender=DepartmentMembership, dispatch_uid="portal.membership_saved")
def _membership_saved(
    sender: Any, instance: DepartmentMembership, created: bool, raw: bool = False, **kw: Any
) -> None:
    if raw:
        return
    change = {
        "department": instance.department.name,
        "is_head": instance.is_head,
        "scope": instance.scope_label,
        "created": created,
    }
    record_change(instance.user, {"department_membership": change}, kind="department_membership")


@receiver(post_delete, sender=DepartmentMembership, dispatch_uid="portal.membership_deleted")
def _membership_deleted(sender: Any, instance: DepartmentMembership, **kw: Any) -> None:
    from accounts.models import User

    user = User._base_manager.filter(pk=instance.user_id).first()
    if user is not None:
        record_change(
            user,
            {"department_membership": {"department": instance.department.name, "removed": True}},
            kind="department_membership",
        )
