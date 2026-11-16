from django import forms

from core.forms import ProtectedFormMixin


class SubscribeForm(ProtectedFormMixin):
    email = forms.EmailField(
        widget=forms.EmailInput(attrs={"autocomplete": "email", "placeholder": "you@example.com"})
    )
    name = forms.CharField(max_length=150, required=False, label="First name (optional)")
    consent = forms.BooleanField(
        required=True,
        label="Send me ministry news by email. I can unsubscribe at any time.",
    )
