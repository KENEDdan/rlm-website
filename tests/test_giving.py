"""Phase G: giving, partnership, providers, webhooks, and proof that no card data can be stored."""

from __future__ import annotations

import json
import re
import time
from decimal import Decimal
from pathlib import Path

import pytest
from django.apps import apps
from django.conf import settings
from django.core import mail
from django.test import Client, override_settings

from core.crypto import is_encrypted_token
from giving import services
from giving.models import Donation, GivingCategory, GivingSettings, PartnershipEnquiry, WebhookEvent
from giving.providers import get_provider
from giving.providers.hosted_gateway import HostedCheckoutGateway
from tests.test_forms import raw_value

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _run_on_commit(monkeypatch):  # type: ignore[no-untyped-def]
    """Emails are queued with transaction.on_commit; tests run inside a transaction, so run them now."""
    monkeypatch.setattr("django.db.transaction.on_commit", lambda func, using=None, robust=False: func())


CARD_PATTERNS = re.compile(
    r"(card|pan|cvv|cvc|cvn|expiry|exp_month|exp_year|security_code|magstripe|track[12]|pin)", re.I
)
ALLOWED = {"pin": set()}  # no exceptions


def test_no_model_in_the_project_has_card_fields() -> None:
    offenders = []
    for model in apps.get_models():
        for field in model._meta.get_fields():
            name = getattr(field, "name", "")
            if CARD_PATTERNS.search(name) and not name.endswith("_set"):
                offenders.append(f"{model._meta.label}.{name}")
    assert offenders == [], offenders


def test_no_card_fields_in_any_form_or_template() -> None:
    from giving.forms import PartnershipForm, PledgeForm

    for form in (PledgeForm, PartnershipForm):
        assert not [f for f in form.base_fields if CARD_PATTERNS.search(f)]
    for path in Path(settings.BASE_DIR, "templates").rglob("*.html"):
        text = path.read_text(encoding="utf-8").lower()
        assert 'name="card' not in text and 'name="cvv' not in text and "cc-number" not in text, path


def test_no_bank_details_hardcoded_or_seeded() -> None:
    gs = GivingSettings.load()
    assert not (gs.account_number or gs.account_name or gs.bank_name or gs.swift_code)
    assert not gs.bank_transfer_enabled
    swift_like = re.compile(r"\b[A-Z]{4}SS[A-Z0-9]{2}([A-Z0-9]{3})?\b")
    for folder in ("templates", "giving", "core"):
        for path in Path(settings.BASE_DIR, folder).rglob("*"):
            if path.suffix in {".py", ".html", ".txt", ".json"}:
                assert not swift_like.search(path.read_text(encoding="utf-8")), path


def test_give_page_shows_bank_details_only_when_complete(client: Client) -> None:
    assert b"Bank details coming soon" in client.get("/give/").content
    gs = GivingSettings.load()
    gs.bank_transfer_enabled = True
    gs.account_name = "Example Ministry Account"
    gs.bank_name = "Example Bank"
    gs.account_number = "000-TEST-000"
    with pytest.raises(PermissionError):  # bank details only change through the confirmed flow
        gs.save()
    gs._bank_change_confirmed = (
        True  # what giving.bank_details.confirm() does after the second person confirms
    )
    gs.save()
    html = client.get("/give/").content
    assert b"000-TEST-000" in html and b"Example Bank" in html
    assert is_encrypted_token(raw_value(GivingSettings, 1, "account_number"))


def test_categories_seeded() -> None:
    names = set(GivingCategory.objects.values_list("slug", flat=True))
    assert {"general-support", "equipment-and-facilities", "discipleship"} <= names


def pledge(client: Client, **kw: object):  # type: ignore[no-untyped-def]
    data = {
        "amount": "50.00",
        "currency": "USD",
        "donor_name": "Donor Example",
        "donor_email": "donor@example.test",
        "transfer_reference": "REF123",
        "consent": "on",
    }
    data.update(kw)
    return client.post("/give/pledge/", data)


def test_manual_pledge_flow_and_finance_confirmation(client: Client, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import FINANCE, MEMBERSHIP

    assert pledge(client).status_code == 302
    d = Donation.objects.get()
    assert d.status == "pledged" and d.provider == "manual_bank" and d.receipt_number is None
    for column in ("donor_name", "donor_email", "transfer_reference"):
        assert is_encrypted_token(raw_value(Donation, d.pk, column))
    assert any(m.to == ["donor@example.test"] for m in mail.outbox)

    secretary = verified_client(make_staff(MEMBERSHIP))
    assert (
        secretary.post(
            "/test-portal/giving/donation/", {"action": "confirm_received", "_selected_action": [d.pk]}
        ).status_code
        == 403
    )

    user = make_staff(FINANCE)
    finance = verified_client(user)
    mail.outbox.clear()
    finance.post("/test-portal/giving/donation/", {"action": "confirm_received", "_selected_action": [d.pk]})
    d.refresh_from_db()
    assert d.status == "confirmed" and d.confirmed_by == user and d.receipt_number.startswith("RLM-")
    receipt = next(m for m in mail.outbox if m.to == ["donor@example.test"])
    assert d.receipt_number in receipt.body
    # idempotent
    assert services.confirm_donation(d) is False


def test_pledge_validation(client: Client) -> None:
    assert pledge(client, amount="-5").status_code == 200
    assert pledge(client, amount="abc").status_code == 200
    assert pledge(client, currency="BTC").status_code == 200
    assert not Donation.objects.exists()


def test_partnership_enquiry(client: Client) -> None:
    data = {
        "partner_type": "church",
        "name": "Example Church",
        "email": "church@example.test",
        "phone": "+254 700 000 001",
        "country": "Kenya",
        "city": "Nairobi",
        "areas": ["evangelism"],
        "partnership_types": ["prayer"],
        "message": "We want to partner",
        "consent": "on",
    }
    assert client.post("/partner/", data).status_code == 302
    e = PartnershipEnquiry.objects.get()
    for field in ("name", "email", "phone", "message"):
        assert is_encrypted_token(raw_value(PartnershipEnquiry, e.pk, field))


def test_provider_registry() -> None:
    assert get_provider("manual_bank").name.startswith("Bank")
    with pytest.raises(LookupError):
        get_provider("nope")
    with pytest.raises(NotImplementedError):
        HostedCheckoutGateway().start_checkout(Donation(amount=1), None)  # type: ignore[arg-type]


# ------------------------------------------------------------------ webhooks
SECRET = "whsec_test_only"  # pragma: allowlist secret


def signed(client: Client, payload: dict, *, secret: str = SECRET, ts: int | None = None, sig: str | None = None):  # type: ignore[no-untyped-def]
    body = json.dumps(payload).encode()
    ts = ts or int(time.time())
    signature = sig or HostedCheckoutGateway.expected_signature(secret, str(ts), body)
    return client.post(
        "/payments/webhook/gateway/",
        data=body,
        content_type="application/json",
        HTTP_X_GATEWAY_SIGNATURE=signature,
        HTTP_X_GATEWAY_TIMESTAMP=str(ts),
    )


@pytest.fixture
def gateway_on() -> Donation:
    gs = GivingSettings.load()
    gs.gateway_enabled = True
    gs.save()
    d = Donation.objects.create(amount=Decimal("25.00"), currency="USD", provider="gateway", status="pending")
    Donation.objects.filter(pk=d.pk).update(provider_reference="gw_ref_1")
    return d


EVENT = {
    "id": "evt_1",
    "type": "payment.updated",
    "data": {"reference": "gw_ref_1", "status": "succeeded", "amount": "25.00", "currency": "USD"},
}


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_webhook_valid_signature_is_idempotent(client: Client, gateway_on: Donation) -> None:
    first = signed(client, EVENT)
    assert first.status_code == 200 and first.json()["duplicate"] is False
    gateway_on.refresh_from_db()
    assert gateway_on.status == "confirmed" and gateway_on.receipt_number
    receipt = gateway_on.receipt_number
    second = signed(client, EVENT)
    assert second.json()["duplicate"] is True
    gateway_on.refresh_from_db()
    assert gateway_on.receipt_number == receipt and WebhookEvent.objects.count() == 1


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_webhook_rejects_bad_signature_stale_and_mismatch(client: Client, gateway_on: Donation) -> None:
    assert signed(client, EVENT, secret="wrong").status_code == 400  # pragma: allowlist secret
    assert signed(client, EVENT, sig="deadbeef").status_code == 400
    assert signed(client, EVENT, ts=int(time.time()) - 3600).status_code == 400
    tampered = {**EVENT, "id": "evt_2", "data": {**EVENT["data"], "amount": "1.00"}}
    assert signed(client, tampered).status_code == 200
    gateway_on.refresh_from_db()
    assert gateway_on.status == "pending"  # amount mismatch ignored


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": ""})
def test_webhook_without_secret_rejected(client: Client, gateway_on: Donation) -> None:
    assert signed(client, EVENT).status_code == 400


def test_webhook_404_when_gateway_disabled_or_unknown(client: Client) -> None:
    assert (
        client.post("/payments/webhook/gateway/", data=b"{}", content_type="application/json").status_code
        == 404
    )
    gs = GivingSettings.load()
    gs.gateway_enabled = True
    gs.save()
    assert (
        client.post("/payments/webhook/manual_bank/", data=b"{}", content_type="application/json").status_code
        == 404
    )
    assert (
        client.post("/payments/webhook/unknown/", data=b"{}", content_type="application/json").status_code
        == 404
    )
    assert client.get("/payments/webhook/gateway/").status_code == 405


def test_giving_settings_only_founder_and_finance_in_admin(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import FINANCE, MEDIA

    assert (
        verified_client(make_staff(MEDIA)).get("/test-portal/giving/givingsettings/1/change/").status_code
        == 403
    )
    assert (
        verified_client(make_staff(FINANCE)).get("/test-portal/giving/givingsettings/1/change/").status_code
        == 200
    )
