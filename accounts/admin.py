from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group
from django.http import HttpRequest
from django_otp.plugins.otp_totp.models import TOTPDevice

from core.admin_mixins import AuditedAdminMixin

from .models import User


@admin.register(User)
class UserAdmin(AuditedAdminMixin, BaseUserAdmin):
    """READ-ONLY, Super Admin only. Accounts and roles are managed in the staff portal (Accounts), where the
    rules live: re-authentication, invite-only onboarding, Super Admin limit, last-Super-Admin protection,
    session kill and full audit. Editing here would bypass them, so nobody - superusers included - can add,
    change or delete users in the Django admin."""

    ordering = ("email",)
    list_display = (
        "email",
        "full_name",
        "is_active",
        "is_superuser",
        "role_names",
        "has_2fa",
        "last_login",
    )
    list_filter = ("is_active", "is_superuser", "groups")
    search_fields = ("email", "full_name")
    fieldsets = (
        (None, {"fields": ("email", "full_name")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Scope", {"fields": ("branch",)}),
        (
            "History",
            {
                "fields": (
                    "last_login",
                    "date_joined",
                    "deactivated_at",
                    "deleted_at",
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )
    readonly_fields = tuple(f for _, opts in fieldsets for f in opts["fields"])
    actions = None

    @admin.display(description="Roles")
    def role_names(self, obj: User) -> str:
        return ", ".join(obj.groups.values_list("name", flat=True))

    @admin.display(boolean=True, description="2FA")
    def has_2fa(self, obj: User) -> bool:
        return TOTPDevice.objects.filter(user=obj, confirmed=True).exists()

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

    def get_urls(self) -> list[Any]:
        # Drop the admin's "change password of another user" screen entirely.
        return [u for u in super().get_urls() if "password" not in str(u.pattern)]


# Groups are managed in code (accounts/roles.py). Show them read-only to the Founder.
admin.site.unregister(Group)


@admin.register(Group)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name",)
    filter_horizontal = ("permissions",)

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


# django-otp's own device admins expose TOTP secrets; 2FA is managed via the "Reset two-factor" action only.
def _unregister_otp_admins() -> None:
    from django_otp.plugins.otp_static.models import StaticDevice

    for model in (TOTPDevice, StaticDevice):
        if admin.site.is_registered(model):
            admin.site.unregister(model)


_unregister_otp_admins()
