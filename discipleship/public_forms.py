"""Public 'Discipleship Registration' form (docs/membership_policy_questionnaire.md, form 2)."""

from __future__ import annotations

from typing import Any

from django import forms

from core.forms import (
    GUARDIAN_REQUIRED,
    MINOR_HELP,
    ApplicationRetentionNotice,
    ConsentMixin,
    ProtectedFormMixin,
    SectionedFormMixin,
)
from core.models import phone_validator
from core.people import ADULT_AGE, Gender, YesNo

from .models import GrowthArea, Registration


class DiscipleshipRegistrationForm(
    SectionedFormMixin, ProtectedFormMixin, ApplicationRetentionNotice, ConsentMixin, forms.Form
):
    full_name = forms.CharField(
        max_length=150, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    gender = forms.ChoiceField(choices=Gender.choices, widget=forms.RadioSelect, label="Gender")
    age = forms.IntegerField(
        min_value=5, max_value=120, label="Age", widget=forms.NumberInput(attrs={"inputmode": "numeric"})
    )
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
    email = forms.EmailField(
        required=False,
        label="Email address (optional)",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    born_again = forms.ChoiceField(
        choices=YesNo.choices, widget=forms.RadioSelect, label="Are you born again?"
    )
    baptized = forms.ChoiceField(
        choices=YesNo.choices, widget=forms.RadioSelect, label="Are you baptized in water?"
    )
    attends_church = forms.ChoiceField(
        choices=YesNo.choices, widget=forms.RadioSelect, label="Are you currently attending a church?"
    )
    journey = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 6}),
        label="Briefly share your spiritual journey, why you want to join the discipleship program, and what you "
        "desire to achieve spiritually.",
    )
    growth_areas = forms.MultipleChoiceField(
        choices=GrowthArea.choices,
        widget=forms.CheckboxSelectMultiple,
        label="Which area would you particularly like to grow in?",
    )
    guardian_name = forms.CharField(max_length=150, required=False, label="Parent or guardian's name")
    guardian_contact = forms.CharField(
        max_length=100, required=False, label="Parent or guardian's phone or email"
    )
    guardian_consent = forms.BooleanField(
        required=False, label="My parent or guardian agrees to this registration."
    )

    sections = [
        (
            "A. Personal information",
            ["full_name", "gender", "age", "nationality", "country", "city", "phone", "email"],
            "",
        ),
        ("B. Spiritual background", ["born_again", "baptized", "attends_church"], ""),
        ("C. Personal statement", ["journey", "growth_areas"], ""),
        ("Under 18?", ["guardian_name", "guardian_contact", "guardian_consent"], MINOR_HELP),
    ]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        age = cleaned.get("age")
        if (
            age is not None
            and age < ADULT_AGE
            and not (
                cleaned.get("guardian_name")
                and cleaned.get("guardian_contact")
                and cleaned.get("guardian_consent")
            )
        ):
            raise forms.ValidationError(GUARDIAN_REQUIRED)
        return cleaned

    def save(self) -> Registration:
        data = self.cleaned_data
        adult = data["age"] >= ADULT_AGE
        return Registration.objects.create(
            full_name=data["full_name"],
            gender=data["gender"],
            age=str(data["age"]),
            nationality=data["nationality"],
            country=data["country"],
            city=data["city"],
            phone=data["phone"],
            email=data["email"],
            born_again=data["born_again"],
            baptized=data["baptized"],
            attends_church=data["attends_church"],
            journey=data["journey"],
            growth_areas=list(data["growth_areas"]),
            guardian_name="" if adult else data["guardian_name"],
            guardian_contact="" if adult else data["guardian_contact"],
            guardian_consent=False if adult else bool(data["guardian_consent"]),
            consent=True,
        )
