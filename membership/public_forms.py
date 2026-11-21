"""Public 'Membership Registration' form (docs/membership_policy_questionnaire.md, form 1)."""

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
from core.people import ADULT_AGE, Gender, YesNo, age_on

from .models import Member


class MembershipRegistrationForm(
    SectionedFormMixin, ProtectedFormMixin, ApplicationRetentionNotice, ConsentMixin, forms.Form
):
    full_name = forms.CharField(
        max_length=150, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    gender = forms.ChoiceField(choices=Gender.choices, widget=forms.RadioSelect, label="Gender")
    date_of_birth = forms.DateField(
        label="Date of birth", widget=forms.DateInput(attrs={"type": "date", "autocomplete": "bday"})
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
    occupation = forms.CharField(max_length=150, label="Current occupation")
    born_again = forms.ChoiceField(
        choices=YesNo.choices, widget=forms.RadioSelect, label="Are you born again?"
    )
    church_attended = forms.CharField(max_length=200, label="Which church do you attend?")
    years_christian = forms.CharField(max_length=60, label="How long have you been a Christian?")
    testimony = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 6}),
        label="Briefly introduce yourself, share your testimony of your conversion, and explain why you would like "
        "to become a member of Rebuilding Lives Ministry.",
    )
    talents = forms.CharField(
        max_length=2000,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="What talents, skills, or gifts would you like to contribute to the ministry?",
    )
    guardian_name = forms.CharField(max_length=150, required=False, label="Parent or guardian's name")
    guardian_contact = forms.CharField(
        max_length=100, required=False, label="Parent or guardian's phone or email"
    )
    guardian_consent = forms.BooleanField(
        required=False, label="My parent or guardian agrees to this registration."
    )
    declaration = forms.BooleanField(
        label="I agree to uphold the vision, mission, values, and principles of Rebuilding Lives Ministry."
    )
    comms_opt_in = forms.BooleanField(
        required=False,
        label="Send me ministry announcements by email or WhatsApp (optional; you can stop any time).",
    )

    sections = [
        (
            "A. Personal information",
            [
                "full_name",
                "gender",
                "date_of_birth",
                "nationality",
                "country",
                "city",
                "phone",
                "email",
                "occupation",
            ],
            "",
        ),
        ("B. Christian background", ["born_again", "church_attended", "years_christian"], ""),
        ("C. Personal statement", ["testimony", "talents"], ""),
        ("Under 18?", ["guardian_name", "guardian_contact", "guardian_consent"], MINOR_HELP),
        ("Declaration", ["declaration", "comms_opt_in"], ""),
    ]

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        age = age_on(cleaned.get("date_of_birth"))
        if age is not None and (age < 5 or age > 120):
            self.add_error("date_of_birth", "Please check the date of birth.")
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

    def save(self) -> Member:
        data = self.cleaned_data
        adult = (age_on(data["date_of_birth"]) or 0) >= ADULT_AGE
        return Member.objects.create(
            status=Member.Status.SUBMITTED,
            source=Member.Source.WEBSITE,
            full_name=data["full_name"],
            gender=data["gender"],
            date_of_birth=data["date_of_birth"].isoformat(),
            nationality=data["nationality"],
            country=data["country"],
            city=data["city"],
            phone=data["phone"],
            email=data["email"],
            occupation=data["occupation"],
            born_again=data["born_again"],
            church_attended=data["church_attended"],
            years_christian=data["years_christian"],
            testimony=data["testimony"],
            talents=data["talents"],
            declaration=True,
            consent=True,
            # Under-18s are never put on announcement lists, whatever was ticked.
            comms_opt_in=bool(data.get("comms_opt_in")) and adult,
            guardian_name="" if adult else data["guardian_name"],
            guardian_contact="" if adult else data["guardian_contact"],
            guardian_consent=False if adult else bool(data["guardian_consent"]),
        )
