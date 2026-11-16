from __future__ import annotations

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin
from core.models import phone_validator

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
    subject = forms.CharField(max_length=150)
    message = forms.CharField(max_length=4000, widget=forms.Textarea(attrs={"rows": 6}))

    class Meta:
        model = ContactMessage
        fields = ["name", "email", "phone", "topic", "subject", "message"]

    def save(self, commit: bool = True) -> ContactMessage:
        obj = super().save(commit=False)
        obj.consent = True
        if commit:
            obj.save()
        return obj
