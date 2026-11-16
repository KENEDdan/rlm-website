from __future__ import annotations

from django.http import HttpRequest

from ..models import Donation, GivingSettings
from .base import CheckoutResult, PaymentProvider


class ManualBankTransfer(PaymentProvider):
    """Works today: the donor gives by bank transfer or mobile money, then submits an 'I have given'
    pledge. Finance checks the bank statement and confirms it in the admin, which issues the receipt."""

    code = Donation.Provider.MANUAL_BANK
    name = "Bank transfer / mobile money"

    def start_checkout(self, donation: Donation, request: HttpRequest) -> CheckoutResult:
        donation.status = Donation.Status.PLEDGED
        donation.provider = self.code
        donation.save(update_fields=["status", "provider", "updated_at"])
        return CheckoutResult(
            template="giving/thank_you.html", context={"settings_obj": GivingSettings.load()}
        )
