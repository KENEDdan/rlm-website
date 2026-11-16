"""Append-only audit log (CLAUDE.md rule 6).

Rows can only be inserted. ``save()`` on an existing row and ``delete()`` raise, the admin is read-only,
and a PostgreSQL trigger (migration 0002) rejects UPDATE/DELETE at the database level too.
"""

from __future__ import annotations

from typing import Any, ClassVar

from django.db import models


class AuditLogQuerySet(models.QuerySet):
    def update(self, **kwargs: Any) -> int:
        raise PermissionError("Audit log rows are immutable.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise PermissionError("Audit log rows cannot be deleted.")


class AuditLog(models.Model):
    class Action(models.TextChoices):
        LOGIN = "login", "Login"
        LOGIN_FAILED = "login_failed", "Login failed"
        LOGOUT = "logout", "Logout"
        TWO_FACTOR_SETUP = "2fa_setup", "2FA set up"
        TWO_FACTOR_FAILED = "2fa_failed", "2FA failed"
        TWO_FACTOR_RESET = "2fa_reset", "2FA reset"
        VIEW = "view", "Viewed"
        ADD = "add", "Added"
        CHANGE = "change", "Changed"
        DELETE = "delete", "Deleted"
        EXPORT = "export", "Exported"
        PRIVACY_EXPORT = "privacy_export", "Personal data exported"
        PRIVACY_ERASE = "privacy_erase", "Personal data erased"
        PURGE = "purge", "Retention purge"
        KEY_ROTATION = "key_rotation", "Encryption key rotation"

    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)
    actor_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    actor_email = models.CharField(max_length=254, blank=True)
    action = models.CharField(max_length=32, choices=Action.choices, db_index=True)
    app_label = models.CharField(max_length=100, blank=True)
    model = models.CharField(max_length=100, blank=True)
    object_id = models.CharField(max_length=64, blank=True)
    object_repr = models.CharField(max_length=200, blank=True, help_text="Never contains personal data.")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=200, blank=True)
    extra = models.JSONField(default=dict, blank=True)

    objects = AuditLogQuerySet.as_manager()

    class Meta:
        ordering: ClassVar = ["-timestamp"]
        verbose_name = "audit log entry"
        verbose_name_plural = "audit log"
        default_permissions = ("view",)

    def __str__(self) -> str:
        return f"{self.timestamp:%Y-%m-%d %H:%M} {self.actor_email or 'system'} {self.action} {self.model} {self.object_id}"

    def save(self, *args: Any, **kwargs: Any) -> None:
        if self.pk is not None:
            raise PermissionError("Audit log rows are immutable.")
        super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise PermissionError("Audit log rows cannot be deleted.")
