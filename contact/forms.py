from __future__ import annotations

from typing import Any

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin
from core.models import phone_validator
from core.site_text import option_choices

from .models import ContactMessage


class ContactForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(
        max_length=30,
        required=False,
        validators=[phone_validator],
        label="Phone (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    category = forms.ChoiceField(
        choices=ContactMessage.Category.choices,
        initial=ContactMessage.Category.GENERAL,
        required=False,  # missing = General
        label="Subject",
        widget=forms.RadioSelect,
        help_text="Giving, finance and partnership messages go straight to our Finance team.",
    )
    topic = forms.ChoiceField(choices=(), label="Topic")
    subject = forms.CharField(max_length=150, label="Short summary")
    message = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 6}))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "category", "topic", "subject", "message"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["topic"].choices = option_choices("contact_topic")
        self.order_fields([*self.Meta.fields, "consent", "website"])

    def clean_category(self) -> str:
        return self.cleaned_data.get("category") or ContactMessage.Category.GENERAL

    def save(self, commit: bool = True) -> ContactMessage:
        obj = super().save(commit=False)
        obj.consent = True
        if commit:
            obj.save()
        return obj
