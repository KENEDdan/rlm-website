"""Forms for the Super Admin's account screens in the portal."""

from __future__ import annotations

from typing import Any

from django import forms

from branches.models import Branch

from .roles import BRANCH_COORDINATOR, DEPARTMENTS, EXECUTIVE
from .services import RoleSpec

DEPT_CHOICES = [("", "No role"), ("member", "Member"), ("head", "Head")]


class RoleFieldsMixin(forms.Form):
    branch = forms.ModelChoiceField(
        queryset=Branch.objects.all(),
        required=False,
        help_text="Required for Branch Coordinators. Limits them to this branch's records.",
    )
    branch_coordinator = forms.BooleanField(required=False, label="Branch Coordinator")
    executive = forms.BooleanField(
        required=False, label="Executive Leadership (sees the Executive Overview: totals only)"
    )
    super_admin = forms.BooleanField(
        required=False,
        label="Super Admin (Founder): full access, including all accounts",
        help_text="At most two active Super Admins are allowed.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        for code, name in DEPARTMENTS:
            self.fields[f"dept_{code}"] = forms.ChoiceField(choices=DEPT_CHOICES, required=False, label=name)

    def department_fields(self) -> list[Any]:
        return [self[f"dept_{code}"] for code, _ in DEPARTMENTS]

    def other_fields(self) -> list[Any]:
        return [self[n] for n in ("branch", "branch_coordinator", "executive", "super_admin")]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("branch_coordinator") and not cleaned.get("branch"):
            self.add_error("branch", "A Branch Coordinator must be linked to a branch.")
        return cleaned

    def spec(self) -> RoleSpec:
        data = self.cleaned_data
        departments = {
            code: data[f"dept_{code}"] == "head" for code, _ in DEPARTMENTS if data.get(f"dept_{code}")
        }
        extra = set()
        if data.get("branch_coordinator"):
            extra.add(BRANCH_COORDINATOR)
        if data.get("executive"):
            extra.add(EXECUTIVE)
        branch = data.get("branch")
        return RoleSpec(
            departments=departments,
            extra_roles=extra,
            branch_id=branch.pk if branch else None,
            super_admin=bool(data.get("super_admin")),
        )

    @staticmethod
    def initial_from(spec: RoleSpec) -> dict[str, Any]:
        initial: dict[str, Any] = {
            "branch": spec.branch_id,
            "branch_coordinator": BRANCH_COORDINATOR in spec.extra_roles,
            "executive": EXECUTIVE in spec.extra_roles,
            "super_admin": spec.super_admin,
        }
        for code, is_head in spec.departments.items():
            initial[f"dept_{code}"] = "head" if is_head else "member"
        return initial


class InviteForm(RoleFieldsMixin):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField(help_text="The invitation goes ONLY to this address.")

    field_order = ["full_name", "email"]


class RolesForm(RoleFieldsMixin):
    pass
