"""Payment providers. See base.PaymentProvider and docs/GIVING_GATEWAYS.md."""

from __future__ import annotations

from .base import PaymentProvider
from .hosted_gateway import HostedCheckoutGateway
from .manual import ManualBankTransfer

PROVIDERS: dict[str, type[PaymentProvider]] = {
    ManualBankTransfer.code: ManualBankTransfer,
    HostedCheckoutGateway.code: HostedCheckoutGateway,
}


def get_provider(code: str) -> PaymentProvider:
    try:
        return PROVIDERS[code]()
    except KeyError as exc:
        raise LookupError(f"Unknown payment provider '{code}'") from exc
