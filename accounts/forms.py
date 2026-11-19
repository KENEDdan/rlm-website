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


class ChoosePasswordForm(forms.Form):
    """Invite / forced reset: the person chooses their own password (all password validators apply)."""

    password1 = forms.CharField(
        label="New password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        help_text="At least 12 characters, mixing letters, numbers and symbols. Do not reuse another password.",
    )
    password2 = forms.CharField(
        label="New password again",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
    )

    def __init__(self, *args: Any, user: Any, **kwargs: Any) -> None:
        self.user = user
        super().__init__(*args, **kwargs)

    def clean(self) -> dict[str, Any]:
        from django.contrib.auth.password_validation import validate_password

        cleaned = super().clean()
        p1, p2 = cleaned.get("password1"), cleaned.get("password2")
        if p1 and p2 and p1 != p2:
            raise forms.ValidationError("The two passwords do not match.")
        if p1:
            try:
                validate_password(p1, user=self.user)
            except forms.ValidationError as exc:
                self.add_error("password1", exc)
        return cleaned


class ReauthForm(forms.Form):
    password = forms.CharField(
        label="Your password",
        strip=False,
        widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}),
    )
    code = forms.CharField(
        label="Authentication code",
        max_length=16,
        widget=forms.TextInput(attrs={"autocomplete": "one-time-code", "inputmode": "numeric"}),
        help_text="The 6-digit code from your authenticator app.",
    )
