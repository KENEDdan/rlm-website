from __future__ import annotations

from typing import Any

from django import forms
from django.contrib.auth import authenticate
from django.http import HttpRequest

GENERIC_LOGIN_ERROR = "Email or password is incorrect, or the account is not allowed to sign in."


class StaffLoginForm(forms.Form):
    username = forms.EmailField(label="Email", widget=forms.EmailInput(attrs={"autocomplete": "username"}))
    password = forms.CharField(
        label="Password", strip=False, widget=forms.PasswordInput(attrs={"autocomplete": "current-password"})
    )

    def __init__(self, *args: Any, request: HttpRequest, **kwargs: Any) -> None:
        self.request = request
        self.user: Any = None
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        email, password = cleaned.get("username"), cleaned.get("password")
        if email and password:
            user = authenticate(self.request, username=email.lower(), password=password)
            if user is None or not user.is_active or not user.is_staff:
                raise forms.ValidationError(GENERIC_LOGIN_ERROR, code="invalid_login")
            self.user = user
        return cleaned


class OTPForm(forms.Form):
    code = forms.CharField(
        label="Authentication code",
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "autofocus": True}),
        help_text="The 6-digit code from your authenticator app, or one of your backup codes.",
    )
