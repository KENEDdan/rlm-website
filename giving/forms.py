from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin
from core.models import phone_validator
from core.site_text import option_choices

from .models import Donation, GivingCategory, PartnershipEnquiry

CURRENCIES = [("USD", "USD"), ("SSP", "SSP"), ("KES", "KES"), ("UGX", "UGX"), ("EUR", "EUR"), ("GBP", "GBP")]


class PledgeForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    """'I have given' notice for bank transfer / mobile money. No card or account data is collected."""

    amount = forms.DecimalField(min_value=Decimal("0.01"), max_value=Decimal("1000000"), decimal_places=2)
    currency = forms.ChoiceField(choices=CURRENCIES)
    category = forms.ModelChoiceField(
        queryset=GivingCategory.objects.none(), required=False, empty_label="Where most needed"
    )
    donor_name = forms.CharField(
        max_length=150,
        required=False,
        label="Your name (optional)",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    donor_email = forms.EmailField(
        required=False,
        label="Email for your receipt (optional)",
        widget=forms.EmailInput(attrs={"autocomplete": "email"}),
    )
    donor_phone = forms.CharField(
        max_length=30, required=False, validators=[phone_validator], label="Phone (optional)"
    )
    transfer_reference = forms.CharField(
        max_length=100, required=False, label="Transfer reference you used (optional)"
    )
    donor_message = forms.CharField(
        max_length=1000, required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Message (optional)"
    )

    class Meta:
        model = Donation
        fields = [
            "amount",
            "currency",
            "category",
            "given_on",
            "transfer_reference",
            "donor_name",
            "donor_email",
            "donor_phone",
            "donor_message",
            "is_anonymous",
        ]
        widgets = {"given_on": forms.DateInput(attrs={"type": "date"})}
        labels = {"given_on": "Date you gave (optional)", "is_anonymous": "Please keep my gift anonymous"}

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["category"].queryset = GivingCategory.objects.filter(is_active=True)


class PartnershipForm(ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    name = forms.CharField(max_length=150, widget=forms.TextInput(attrs={"autocomplete": "name"}))
    organisation = forms.CharField(max_length=200, required=False, label="Church or organisation (if any)")
    email = forms.EmailField(widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    phone = forms.CharField(
        max_length=30, required=False, validators=[phone_validator], label="Phone (optional)"
    )
    partner_type = forms.ChoiceField(choices=(), label="I am partnering as")
    interest = forms.ChoiceField(choices=(), label="Main interest")
    message = forms.CharField(
        max_length=3000,
        required=False,
        widget=forms.Textarea(attrs={"rows": 4}),
        label="How would you like to partner? (optional)",
    )

    class Meta:
        model = PartnershipEnquiry
        fields = ["partner_type", "interest", "name", "organisation", "email", "phone", "country", "message"]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["partner_type"].choices = [("", "Choose…"), *option_choices("partner_type")]
        self.fields["interest"].choices = option_choices("partner_interest")
        self.order_fields([*self.Meta.fields, "consent", "website"])

    def save(self, commit: bool = True) -> PartnershipEnquiry:
        obj = super().save(commit=False)
        obj.consent = True
        if commit:
            obj.save()
        return obj
