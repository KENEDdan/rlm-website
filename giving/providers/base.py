"""The PaymentProvider interface.

A provider turns a Donation into either instructions (manual) or a redirect to a HOSTED checkout page
(gateway). Card numbers and mobile-money PINs are only ever typed into the gateway's own page.
Our server never sees or stores them (CLAUDE.md rule 11).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from django.http import HttpRequest

from ..models import Donation


@dataclass
class CheckoutResult:
    """What the view should do next."""

    redirect_url: str | None = None  # hosted checkout page (gateway providers)
    template: str | None = None  # page to render (manual providers)
    context: dict[str, Any] = field(default_factory=dict)


@dataclass
class WebhookOutcome:
    event_id: str
    event_type: str
    provider_reference: str | None = None
    new_status: str | None = None  # a Donation.Status value
    amount: str | None = None
    currency: str | None = None


class WebhookSignatureError(Exception):
    """Raised when a webhook's signature is missing or invalid. The request must be rejected."""


class PaymentProvider(ABC):
    code: str = ""
    name: str = ""
    supports_webhooks: bool = False

    @abstractmethod
    def start_checkout(self, donation: Donation, request: HttpRequest) -> CheckoutResult:
        """Begin a payment for an already-saved Donation."""

    def verify_webhook(self, request: HttpRequest) -> WebhookOutcome:
        """Verify the signature and parse the event. Must raise WebhookSignatureError on any doubt."""
        raise NotImplementedError(f"{self.name} does not accept webhooks.")
