from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest

from .models import AuditLog


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    """Read-only for the Founder. Nobody can add, change or delete entries."""

    list_display = (
        "timestamp",
        "actor_email",
        "action",
        "app_label",
        "model",
        "object_id",
        "object_repr",
        "ip_address",
    )
    list_filter = ("action", "app_label", "model")
    search_fields = ("actor_email", "object_id", "ip_address")
    date_hierarchy = "timestamp"
    list_per_page = 100

    def has_module_permission(self, request: HttpRequest) -> bool:
        return request.user.is_superuser

    def has_view_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.is_superuser

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False

    def get_actions(self, request: HttpRequest) -> dict[str, Any]:
        return {}
