"""Skeleton for a hosted-checkout gateway (cards + mobile money). NOT ACTIVE.

How to finish it when the ministry has chosen a gateway (see docs/GIVING_GATEWAYS.md):

1. ``start_checkout``: call the gateway's "create checkout session" API server-side with amount, currency,
   ``donation.idempotency_key`` as the idempotency/merchant reference, and our success/cancel URLs.
   Save the gateway's session/transaction id in ``donation.provider_reference``, set status PENDING, and
   return ``CheckoutResult(redirect_url=<hosted page url>)``. Card/mobile-money details are entered ONLY on
   the gateway's page.
2. ``verify_webhook``: compute the HMAC of the RAW request body with ``PAYMENT_WEBHOOK_SECRET`` exactly as
   the gateway documents (header name, algorithm, timestamp tolerance), compare with
   ``hmac.compare_digest``, then parse JSON and map the gateway status to a ``Donation.Status``.
3. Never trust the browser redirect ("success" page) to mark a gift paid; only a verified webhook (or a
   server-side status query) may do that.
4. Add the gateway's checkout origin to CSP ``form-action`` / ``frame-src`` only if it is embedded.
5. Add tests with recorded, signed sample payloads before turning ``gateway_enabled`` on.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time

from django.conf import settings
from django.http import HttpRequest

from ..models import Donation
from .base import CheckoutResult, PaymentProvider, WebhookOutcome, WebhookSignatureError

SIGNATURE_HEADER = "HTTP_X_GATEWAY_SIGNATURE"  # replace with the real gateway's header
TIMESTAMP_HEADER = "HTTP_X_GATEWAY_TIMESTAMP"
TOLERANCE_SECONDS = 300
MAX_BODY_BYTES = 64 * 1024

STATUS_MAP = {
    "succeeded": Donation.Status.CONFIRMED,
    "failed": Donation.Status.FAILED,
    "cancelled": Donation.Status.CANCELLED,
    "refunded": Donation.Status.REFUNDED,
    "pending": Donation.Status.PENDING,
}


class HostedCheckoutGateway(PaymentProvider):
    code = Donation.Provider.GATEWAY
    name = "Online gateway (not configured)"
    supports_webhooks = True

    def start_checkout(self, donation: Donation, request: HttpRequest) -> CheckoutResult:
        raise NotImplementedError("No payment gateway has been integrated yet. See this module's docstring.")

    @staticmethod
    def expected_signature(secret: str, timestamp: str, body: bytes) -> str:
        signed = timestamp.encode() + b"." + body
        return hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()

    def verify_webhook(self, request: HttpRequest) -> WebhookOutcome:
        secret = settings.PAYMENT_WEBHOOK_SECRETS.get(self.code, "")
        if not secret:
            raise WebhookSignatureError("Webhook secret not configured.")
        body = request.body
        if len(body) > MAX_BODY_BYTES:
            raise WebhookSignatureError("Payload too large.")
        signature = request.META.get(SIGNATURE_HEADER, "")
        timestamp = request.META.get(TIMESTAMP_HEADER, "")
        if not signature or not timestamp.isdigit():
            raise WebhookSignatureError("Missing signature.")
        if abs(time.time() - int(timestamp)) > TOLERANCE_SECONDS:
            raise WebhookSignatureError("Stale webhook (possible replay).")
        if not hmac.compare_digest(self.expected_signature(secret, timestamp, body), signature):
            raise WebhookSignatureError("Bad signature.")
        try:
            data = json.loads(body)
            event_id = str(data["id"])[:120]
            event_type = str(data.get("type", ""))[:80]
            obj = data.get("data", {})
        except (ValueError, KeyError, TypeError) as exc:
            raise WebhookSignatureError("Malformed payload.") from exc
        return WebhookOutcome(
            event_id=event_id,
            event_type=event_type,
            provider_reference=str(obj.get("reference", ""))[:120] or None,
            new_status=STATUS_MAP.get(str(obj.get("status", ""))),
            amount=str(obj.get("amount", "")) or None,
            currency=str(obj.get("currency", "")) or None,
        )
