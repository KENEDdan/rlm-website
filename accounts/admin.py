from __future__ import annotations

from typing import Any

from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import Group
from django.db.models import QuerySet
from django.http import HttpRequest
from django_otp.plugins.otp_totp.models import TOTPDevice

from audit.models import AuditLog
from audit.services import log_event
from core.admin_mixins import AuditedAdminMixin

from .models import User
from .roles import BRANCH_COORDINATOR, DEPARTMENT_HEAD
from .twofactor import reset_two_factor


class StaffCreationForm(UserCreationForm):
    class Meta:
        model = User
        fields = ("email", "full_name")


class StaffChangeForm(forms.ModelForm):
    class Meta:
        model = User
        fields = (
            "email",
            "full_name",
            "is_active",
            "is_staff",
            "is_superuser",
            "groups",
            "branch",
            "department",
        )

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        groups = {g.name for g in cleaned.get("groups") or []}
        if BRANCH_COORDINATOR in groups and not cleaned.get("branch"):
            self.add_error("branch", "Branch Coordinators must be linked to a branch.")
        if DEPARTMENT_HEAD in groups and not cleaned.get("department"):
            self.add_error("department", "Departmental Heads must be linked to a department.")
        return cleaned


@admin.register(User)
class UserAdmin(AuditedAdminMixin, BaseUserAdmin):
    form = StaffChangeForm
    add_form = StaffCreationForm
    ordering = ("email",)
    list_display = (
        "email",
        "full_name",
        "is_active",
        "is_staff",
        "is_superuser",
        "role_names",
        "has_2fa",
        "last_login",
    )
    list_filter = ("is_active", "is_staff", "is_superuser", "groups")
    search_fields = ("email", "full_name")
    readonly_fields = ("last_login", "date_joined", "created_at", "updated_at")
    filter_horizontal = ("groups",)
    fieldsets = (
        (None, {"fields": ("email", "full_name", "password")}),
        ("Access", {"fields": ("is_active", "is_staff", "is_superuser", "groups")}),
        ("Scope", {"fields": ("branch", "department")}),
        ("History", {"fields": ("last_login", "date_joined", "created_at", "updated_at")}),
    )
    add_fieldsets = (
        (None, {"classes": ("wide",), "fields": ("email", "full_name", "password1", "password2")}),
    )
    actions = ["reset_2fa"]

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
        return request.user.is_superuser

    def has_change_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.is_superuser

    def has_delete_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return request.user.is_superuser and (obj is None or obj.pk != request.user.pk)

    @admin.action(description="Reset two-factor (user must enrol again at next sign-in)")
    def reset_2fa(self, request: HttpRequest, queryset: QuerySet) -> None:
        if not request.user.is_superuser:
            return
        for user in queryset:
            reset_two_factor(user)
            log_event(AuditLog.Action.TWO_FACTOR_RESET, request=request, obj=user)
        messages.success(request, f"Two-factor reset for {queryset.count()} account(s).")

    def save_model(self, request: HttpRequest, obj: User, form: Any, change: bool) -> None:
        if not change:
            obj.is_staff = True  # every account created here is a staff account
        super().save_model(request, obj, form, change)


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
