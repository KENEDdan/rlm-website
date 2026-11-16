from __future__ import annotations

from typing import Any

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin
from core.models import phone_validator

from .models import PrayerRequest


class PrayerRequestForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    request_text = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 6}),
        label="Your prayer request",
        help_text="Stored encrypted. Only the prayer team can read it.",
    )
    name = forms.CharField(
        max_length=150,
        required=False,
        label="Your name (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    email = forms.EmailField(
        required=False, label="Email (optional)", widget=forms.EmailInput(attrs={"autocomplete": "email"})
    )
    phone = forms.CharField(
        max_length=30,
        required=False,
        validators=[phone_validator],
        label="Phone (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )

    class Meta:
        model = PrayerRequest
        fields = ["request_text", "keep_confidential", "wants_contact", "name", "email", "phone"]
        labels = {
            "keep_confidential": "Keep my request confidential to the prayer team",
            "wants_contact": "I would like someone to contact me",
        }
        help_texts = {"keep_confidential": ""}

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if cleaned.get("wants_contact") and not (cleaned.get("email") or cleaned.get("phone")):
            self.add_error("email", "Please give an email or phone number so we can contact you.")
        return cleaned

    def save(self, commit: bool = True) -> PrayerRequest:
        obj = super().save(commit=False)
        obj.consent = True
        if commit:
            obj.save()
        return obj
