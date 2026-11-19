"""Public 'Finance and Accountability Volunteer Registration' form (questionnaire, form 4).

Submissions go to Finance for vetting (references, interview, decision). Being approved never gives anyone a
staff account or access to financial data: only the Super Admin can create accounts.
"""

from __future__ import annotations

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin, SectionedFormMixin
from core.models import phone_validator
from core.people import Gender, YesNo

from .models import FinanceVolunteer


class FinanceVolunteerForm(SectionedFormMixin, ProtectedFormMixin, ConsentMixin, forms.Form):
    full_name = forms.CharField(
        max_length=150, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    gender = forms.ChoiceField(choices=Gender.choices, widget=forms.RadioSelect, label="Gender")
    nationality = forms.CharField(max_length=100, label="Nationality")
    country = forms.CharField(
        max_length=100,
        label="Country of residence",
        widget=forms.TextInput(attrs={"autocomplete": "country-name"}),
    )
    city = forms.CharField(
        max_length=120,
        label="City of residence",
        widget=forms.TextInput(attrs={"autocomplete": "address-level2"}),
    )
    phone = forms.CharField(
        max_length=30,
        validators=[phone_validator],
        label="Phone / WhatsApp number",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    occupation = forms.CharField(max_length=150, label="Current occupation")
    education_level = forms.CharField(max_length=100, label="Highest level of education")
    field_of_study = forms.CharField(max_length=150, label="Field of study")
    finance_experience = forms.ChoiceField(
        choices=YesNo.choices,
        widget=forms.RadioSelect,
        label="Do you have experience in accounting, bookkeeping, banking, or financial management?",
    )
    computer_skills = forms.CharField(
        max_length=1000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Which computer skills or financial software can you use?",
    )
    statement = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 6}),
        label="Briefly introduce yourself, describe your professional experience, and explain why you would like to "
        "volunteer in the Finance and Accountability Department of Rebuilding Lives Ministry.",
    )
    willing_integrity = forms.ChoiceField(
        choices=YesNo.choices,
        widget=forms.RadioSelect,
        label="Are you willing to serve with honesty, confidentiality, transparency, and accountability?",
    )
    declaration = forms.BooleanField(
        label="I agree to uphold the financial integrity and accountability standards of Rebuilding Lives Ministry."
    )

    sections = [
        (
            "A. Personal information",
            ["full_name", "gender", "nationality", "country", "city", "phone", "email", "occupation"],
            "",
        ),
        (
            "B. Education and professional background",
            ["education_level", "field_of_study", "finance_experience", "computer_skills"],
            "",
        ),
        ("C. Personal statement", ["statement", "willing_integrity"], ""),
        ("Declaration", ["declaration"], ""),
    ]

    def save(self) -> FinanceVolunteer:
        data = {k: v for k, v in self.cleaned_data.items() if k not in ("consent", "website")}
        return FinanceVolunteer.objects.create(**data, consent=True)
