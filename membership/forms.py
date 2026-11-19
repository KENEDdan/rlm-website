"""Staff-side member form (the public registration form lives in membership/public_forms.py)."""

from __future__ import annotations

from typing import Any

from django import forms

from core.people import ADULT_AGE, age_on
from portal.resources import DateInput

from .models import Member

MINOR_GUARDIAN_ERROR = "Under 18: the parent or guardian's name and contact are required."


class MemberForm(forms.ModelForm):
    date_of_birth = forms.DateField(required=False, widget=DateInput(), label="Date of birth")

    class Meta:
        model = Member
        fields = [
            "full_name",
            "gender",
            "date_of_birth",
            "nationality",
            "country",
            "city",
            "branch",
            "phone",
            "email",
            "occupation",
            "born_again",
            "church_attended",
            "years_christian",
            "testimony",
            "talents",
            "comms_opt_in",
            "guardian_name",
            "guardian_contact",
            "guardian_consent",
            "join_date",
            "orientation_date",
            "transferred_to",
            "internal_notes",
        ]
        widgets = {
            "testimony": forms.Textarea(attrs={"rows": 4}),
            "talents": forms.Textarea(attrs={"rows": 3}),
            "internal_notes": forms.Textarea(attrs={"rows": 3}),
            "join_date": DateInput(),
            "orientation_date": DateInput(),
        }

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.birth_date:
            self.initial["date_of_birth"] = self.instance.birth_date

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        born = cleaned.get("date_of_birth")
        age = age_on(born)
        if (
            age is not None
            and age < ADULT_AGE
            and not (cleaned.get("guardian_name") and cleaned.get("guardian_contact"))
        ):
            raise forms.ValidationError(MINOR_GUARDIAN_ERROR)
        cleaned["date_of_birth"] = born.isoformat() if born else ""
        return cleaned

    def _post_clean(self) -> None:
        super()._post_clean()
        self.instance.date_of_birth = self.cleaned_data.get("date_of_birth", "") or ""
