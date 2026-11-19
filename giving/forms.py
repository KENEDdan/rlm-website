from __future__ import annotations

from decimal import Decimal
from typing import Any

from django import forms

from core.forms import ConsentMixin, ProtectedFormMixin, SectionedFormMixin
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


class PartnershipForm(SectionedFormMixin, ProtectedFormMixin, ConsentMixin, forms.ModelForm):
    """'Partnership Registration' form (docs/membership_policy_questionnaire.md, form 3).

    Choice lists are admin-managed (Form options: partner_type, partner_area, partnership_type).
    """

    name = forms.CharField(
        max_length=150,
        label="Full name / organization name",
        widget=forms.TextInput(attrs={"autocomplete": "name"}),
    )
    country = forms.CharField(
        max_length=100, label="Country", widget=forms.TextInput(attrs={"autocomplete": "country-name"})
    )
    city = forms.CharField(
        max_length=120, label="City", widget=forms.TextInput(attrs={"autocomplete": "address-level2"})
    )
    phone = forms.CharField(
        max_length=30,
        validators=[phone_validator],
        label="Phone / WhatsApp number",
        widget=forms.TextInput(attrs={"autocomplete": "tel", "inputmode": "tel"}),
    )
    email = forms.EmailField(label="Email address", widget=forms.EmailInput(attrs={"autocomplete": "email"}))
    partner_type = forms.ChoiceField(choices=(), widget=forms.RadioSelect, label="Partnership category")
    areas = forms.MultipleChoiceField(
        choices=(),
        widget=forms.CheckboxSelectMultiple,
        label="Which area would you like to partner with us in?",
    )
    other_area = forms.CharField(max_length=200, required=False, label="If other, please describe")
    partnership_types = forms.MultipleChoiceField(
        choices=(), widget=forms.CheckboxSelectMultiple, label="What type of partnership would you prefer?"
    )
    message = forms.CharField(
        max_length=4000,
        widget=forms.Textarea(attrs={"rows": 6}),
        label="Briefly introduce yourself or your organization, explain why you wish to partner with Rebuilding Lives "
        "Ministry, and describe how you would like to contribute to our vision.",
    )

    class Meta:
        model = PartnershipEnquiry
        fields = [
            "name",
            "country",
            "city",
            "phone",
            "email",
            "partner_type",
            "areas",
            "other_area",
            "partnership_types",
            "message",
        ]

    sections = [
        ("A. Partner information", ["name", "country", "city", "phone", "email", "partner_type"], ""),
        ("B. Partnership interests", ["areas", "other_area", "partnership_types"], ""),
        ("C. Personal / organizational statement", ["message"], ""),
    ]

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields["partner_type"].choices = option_choices("partner_type")
        self.fields["areas"].choices = option_choices("partner_area")
        self.fields["partnership_types"].choices = option_choices("partnership_type")

    def clean(self) -> dict[str, Any]:
        cleaned = super().clean()
        if "other" in (cleaned.get("areas") or []) and not cleaned.get("other_area"):
            self.add_error("other_area", "Please tell us which other area.")
        return cleaned

    def save(self, commit: bool = True) -> PartnershipEnquiry:
        obj = super().save(commit=False)
        obj.consent = True
        types = obj.partnership_types or []
        # Keep the older single 'main interest' filled for existing reports and filters.
        obj.interest = next(
            (
                code
                for code, kind in (
                    ("financial", "financial"),
                    ("prayer", "prayer"),
                    ("resources", "material"),
                )
                if kind in types
            ),
            "other",
        )
        if commit:
            obj.save()
        return obj
