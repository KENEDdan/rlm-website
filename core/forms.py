"""Shared protection for every public form: honeypot + Turnstile + consent."""

from __future__ import annotations

from typing import Any

from django import forms
from django.http import HttpRequest

from .turnstile import verify_turnstile

HONEYPOT_FIELD = "website"
GENERIC_ERROR = "We could not verify your submission. Please try again."


class ProtectedFormMixin(forms.Form):
    """Mix into public forms. Construct with ``request=``."""

    website = forms.CharField(
        required=False,
        label="Leave this field empty",
        widget=forms.TextInput(attrs={"autocomplete": "off", "tabindex": "-1"}),
    )

    def __init__(self, *args: Any, request: HttpRequest | None = None, **kwargs: Any) -> None:
        self.request = request
        super().__init__(*args, **kwargs)

    @property
    def is_spam(self) -> bool:
        return bool(self.data.get(HONEYPOT_FIELD))

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if self.is_spam:
            raise forms.ValidationError(GENERIC_ERROR, code="honeypot")
        token = self.data.get("cf-turnstile-response", "")
        ip = self.request.META.get("REMOTE_ADDR") if self.request else None
        if not verify_turnstile(token, ip):
            raise forms.ValidationError(GENERIC_ERROR, code="turnstile")
        return cleaned


class ConsentMixin(forms.Form):
    consent = forms.BooleanField(
        required=True,
        label="I agree that the ministry may store and use these details to respond to me, as described in the privacy policy.",
    )


class SectionedFormMixin:
    """``sections = [("A. Personal information", ["full_name", ...], "optional help"), ...]``."""

    sections: list[tuple[str, list[str], str]] = []

    def grouped_sections(self) -> list[dict[str, Any]]:
        return [
            {"title": title, "help": help_text, "fields": [self[name] for name in names if name in self.fields]}  # type: ignore[attr-defined,index]
            for title, names, help_text in self.sections
        ]


MINOR_HELP = "Only if you are under 18: a parent or guardian must agree."
GUARDIAN_REQUIRED = "You are under 18, so we need your parent or guardian's name, contact and consent."
