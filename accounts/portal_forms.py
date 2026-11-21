"""Forms for the Super Admin's account screens in the portal."""

from __future__ import annotations

from typing import Any

from django import forms

from branches.models import Branch

from .roles import BRANCH_COORDINATOR, DEPARTMENTS, EXECUTIVE, TECHNICAL
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
    technical = forms.BooleanField(
        required=False,
        label="Technical Team (Website Administration): website content only",
        help_text="Hero, Vision/Mission drafts, activities, pages, contacts, social links, leaders, gallery layout. "
        "Never finance, donors, members, prayer, discipleship records or accounts.",
    )
    super_admin = forms.BooleanField(
        required=False,
        label="Super Admin (Founder): full access, including all accounts",
        help_text="At most two active Super Admins are allowed.",
    )

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        branch_choices = [("", "All branches")] + [
            (str(b.pk), f"{b.name} only") for b in Branch.objects.all()
        ]
        for code, name in DEPARTMENTS:
            self.fields[f"dept_{code}"] = forms.ChoiceField(choices=DEPT_CHOICES, required=False, label=name)
            self.fields[f"scope_{code}"] = forms.ChoiceField(
                choices=branch_choices, required=False, label=f"{name}: which branches"
            )

    def department_fields(self) -> list[Any]:
        return [self[f"dept_{code}"] for code, _ in DEPARTMENTS]

    def department_rows(self) -> list[tuple[Any, Any]]:
        return [(self[f"dept_{code}"], self[f"scope_{code}"]) for code, _ in DEPARTMENTS]

    def other_fields(self) -> list[Any]:
        return [self[n] for n in ("branch", "branch_coordinator", "executive", "technical", "super_admin")]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("branch_coordinator") and not cleaned.get("branch"):
            self.add_error("branch", "A Branch Coordinator must be linked to a branch.")
        return cleaned

    def spec(self) -> RoleSpec:
        data = self.cleaned_data
        departments = {
            code: (
                data[f"dept_{code}"] == "head",
                int(data[f"scope_{code}"]) if data.get(f"scope_{code}") else None,
            )
            for code, _ in DEPARTMENTS
            if data.get(f"dept_{code}")
        }
        extra = set()
        if data.get("branch_coordinator"):
            extra.add(BRANCH_COORDINATOR)
        if data.get("executive"):
            extra.add(EXECUTIVE)
        if data.get("technical"):
            extra.add(TECHNICAL)
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
            "technical": TECHNICAL in spec.extra_roles,
            "super_admin": spec.super_admin,
        }
        from .services import department_roles

        for code, (is_head, branch_id) in department_roles(spec).items():
            initial[f"dept_{code}"] = "head" if is_head else "member"
            initial[f"scope_{code}"] = str(branch_id) if branch_id else ""
        return initial


class InviteForm(RoleFieldsMixin):
    full_name = forms.CharField(max_length=150)
    email = forms.EmailField(help_text="The invitation goes ONLY to this address.")

    field_order = ["full_name", "email"]


class RolesForm(RoleFieldsMixin):
    pass
