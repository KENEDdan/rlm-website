from __future__ import annotations

from typing import Any

from django import forms

from branches.models import Branch
from core.forms import ConsentMixin, ProtectedFormMixin
from core.models import phone_validator
from core.site_text import option_choices

from .models import EventRegistration, VolunteerApplication

INPUT = "form-input"


class VolunteerForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    full_name = forms.CharField(
        max_length=150, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(
        max_length=30,
        validators=[phone_validator],
        label="Phone / WhatsApp",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    church_affiliation = forms.CharField(
        max_length=200, required=False, label="Church affiliation (optional)"
    )
    # Choices are loaded per request from the admin-managed lists (Form options).
    interests = forms.MultipleChoiceField(
        choices=(), widget=forms.CheckboxSelectMultiple, label="Where would you like to serve?"
    )
    availability = forms.ChoiceField(choices=(), label="Availability")
    skills = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Skills and gifts (optional)",
    )
    previous_experience = forms.CharField(
        max_length=2000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Previous ministry experience (optional)",
    )
    testimony = forms.CharField(
        max_length=4000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="Your testimony (optional)",
        help_text="Kept private and encrypted. It is never published without asking you first.",
    )

    class Meta:
        model = VolunteerApplication
        fields = [
            "full_name",
            "email",
            "phone",
            "country",
            "location",
            "branch",
            "church_affiliation",
            "interests",
            "availability",
            "skills",
            "previous_experience",
            "testimony",
        ]
        labels = {"location": "City or town", "branch": "Nearest branch (optional)"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["interests"].choices = option_choices("volunteer_interest")
        self.fields["availability"].choices = [("", "Choose…"), *option_choices("volunteer_availability")]
        self.fields["branch"].queryset = Branch.objects.published()
        self.fields["branch"].required = False
        self.fields["country"].max_length = 100
        self.order_fields([*self.Meta.fields, "consent", "website"])

    def save(self, commit: bool = True) -> VolunteerApplication:
        obj = super().save(commit=False)
        obj.consent = True
        if commit:
            obj.save()
        return obj


class EventRegistrationForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    full_name = forms.CharField(
        max_length=150, label="Full name", widget=forms.TextInput(attrs={"autocomplete": "name"})
    )
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(
        max_length=30,
        required=False,
        validators=[phone_validator],
        label="Phone (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    attendees = forms.IntegerField(
        min_value=1, max_value=10, initial=1, label="Number of people (including you)"
    )
    notes = forms.CharField(
        max_length=1000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Accessibility needs or questions (optional)",
    )

    class Meta:
        model = EventRegistration
        fields = ["full_name", "email", "phone", "attendees", "notes"]

    def __init__(self, *args: Any, event: Any, **kwargs: Any) -> None:
        self.event = event
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if not self.event.can_register:
            raise forms.ValidationError("Registration for this event is closed.")
        attendees = cleaned.get("attendees") or 1
        if self.event.spots_left is not None and attendees > self.event.spots_left:
            raise forms.ValidationError(f"Only {self.event.spots_left} place(s) are left for this event.")
        return cleaned
