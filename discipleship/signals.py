"""Cross-department handoff: every new convert recorded by Missions becomes a Discipleship follow-up."""

from typing import Any

from django.db.models.signals import post_save
from django.dispatch import receiver

from missions.models import NewConvert

from .services import hand_off


@receiver(post_save, sender=NewConvert, dispatch_uid="discipleship.hand_off_new_convert")
def _new_convert(sender: Any, instance: NewConvert, created: bool, raw: bool = False, **kwargs: Any) -> None:
    if raw:
        return
    follow = hand_off(instance)
    # Keep branch and the minors flag in step if Missions corrects the record later.
    if not created and (follow.branch_id != instance.branch_id or follow.is_minor != instance.is_minor):
        follow.branch_id, follow.is_minor = instance.branch_id, instance.is_minor
        follow.save(update_fields=["branch", "is_minor", "updated_at"])
