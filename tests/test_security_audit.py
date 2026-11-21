"""Phase I: regression tests for every finding fixed in docs/SECURITY_AUDIT.md."""

from __future__ import annotations

import io
import json
from decimal import Decimal
from pathlib import Path
from unittest import mock

import pytest
from cryptography.fernet import Fernet
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import CommandError, call_command
from django.test import Client, override_settings
from PIL import Image

from accounts.roles import MEMBERSHIP
from audit.models import AuditLog
from contact.models import ContactMessage
from core import checks, privacy
from core.crypto import DECRYPTION_FAILED, blind_index, decrypt_str, encrypt_str
from core.turnstile import verify_turnstile
from core.upload_policy import validate_upload
from giving.models import Donation, WebhookEvent
from newsletter.models import Subscriber
from prayer.models import PrayerRequest
from tests.test_forms import raw_value
from tests.test_giving import EVENT, SECRET, signed

pytestmark = pytest.mark.django_db

PERSON = "person@example.test"
OTHER = "someone.else@example.test"


# ------------------------------------------------------------------ I-1 Turnstile must fail closed
@override_settings(TURNSTILE_ENABLED=True, TURNSTILE_SECRET_KEY="")
def test_turnstile_enabled_without_secret_rejects_without_network_call() -> None:
    with mock.patch("core.turnstile.urllib.request.urlopen") as urlopen:
        assert verify_turnstile("token", "203.0.113.5") is False
    urlopen.assert_not_called()


def test_deploy_check_flags_disabled_or_unconfigured_turnstile() -> None:
    with override_settings(TURNSTILE_ENABLED=False):
        assert [m.id for m in checks.turnstile_check(None)] == ["rlm.W001"]
    with override_settings(TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="", TURNSTILE_SECRET_KEY=""):
        assert [m.id for m in checks.turnstile_check(None)] == ["rlm.E001"]
    with override_settings(TURNSTILE_ENABLED=True, TURNSTILE_SITE_KEY="s", TURNSTILE_SECRET_KEY="k"):
        assert checks.turnstile_check(None) == []


def test_production_settings_enable_turnstile_by_default() -> None:
    source = Path("config/settings/prod.py").read_text(encoding="utf-8")
    assert 'TURNSTILE_ENABLED = env.bool("TURNSTILE_ENABLED", default=True)' in source


# ------------------------------------------------------------------ I-2 webhook atomicity
@pytest.fixture
def gateway_donation() -> Donation:
    from giving.models import GivingSettings

    gs = GivingSettings.load()
    gs.gateway_enabled = True
    gs.save()
    d = Donation.objects.create(amount=Decimal("25.00"), currency="USD", provider="gateway", status="pending")
    Donation.objects.filter(pk=d.pk).update(provider_reference="gw_ref_1")
    return d


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_failed_webhook_is_not_swallowed_on_retry(gateway_donation: Donation) -> None:
    client = Client(raise_request_exception=False)
    with mock.patch("giving.services.apply_webhook", side_effect=RuntimeError("db hiccup")):
        assert signed(client, EVENT).status_code == 500
    assert WebhookEvent.objects.count() == 0  # rolled back with the failure
    retry = signed(client, EVENT)
    assert retry.status_code == 200 and retry.json()["duplicate"] is False
    gateway_donation.refresh_from_db()
    assert gateway_donation.status == Donation.Status.CONFIRMED
    assert WebhookEvent.objects.get().processed is True


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_unprocessed_event_from_older_code_is_reapplied(client: Client, gateway_donation: Donation) -> None:
    WebhookEvent.objects.create(provider="gateway", event_id=EVENT["id"], event_type="x", payload_sha256="0")
    assert signed(client, EVENT).json()["duplicate"] is True
    gateway_donation.refresh_from_db()
    assert gateway_donation.status == Donation.Status.CONFIRMED


# ------------------------------------------------------------------ I-6 webhook scoping
@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_webhook_cannot_touch_donations_of_another_provider(
    client: Client, gateway_donation: Donation
) -> None:
    manual = Donation.objects.create(amount=Decimal("25.00"), currency="USD", provider="manual_bank")
    Donation.objects.filter(pk=gateway_donation.pk).update(provider_reference="other")
    Donation.objects.filter(pk=manual.pk).update(provider_reference="gw_ref_1")
    signed(client, EVENT)
    manual.refresh_from_db()
    assert manual.status == Donation.Status.PLEDGED


@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_webhook_confirmation_requires_amount(client: Client, gateway_donation: Donation) -> None:
    no_amount = {**EVENT, "data": {"reference": "gw_ref_1", "status": "succeeded"}}
    assert signed(client, no_amount).status_code == 200
    gateway_donation.refresh_from_db()
    assert gateway_donation.status == Donation.Status.PENDING
    assert WebhookEvent.objects.get().processed is True


# ------------------------------------------------------------------ I-3 key rotation
def test_rotate_encryption_keys_reencrypts_and_rebuilds_blind_index() -> None:
    old, new = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    with override_settings(FIELD_ENCRYPTION_KEYS=[old]):
        pr = PrayerRequest.objects.create(request_text="heal my mother", email=PERSON, consent=True)
        before = raw_value(PrayerRequest, pr.pk, "request_text")
    with override_settings(FIELD_ENCRYPTION_KEYS=[new, old], BLIND_INDEX_KEY="rotated-index-key"):
        call_command("rotate_encryption_keys", "--dry-run", stdout=io.StringIO())
        assert raw_value(PrayerRequest, pr.pk, "request_text") == before  # dry run wrote nothing
        call_command("rotate_encryption_keys", stdout=io.StringIO())
        assert raw_value(PrayerRequest, pr.pk, "email_hash") == blind_index(PERSON)
        after = raw_value(PrayerRequest, pr.pk, "request_text")
    assert after != before
    with override_settings(FIELD_ENCRYPTION_KEYS=[new]):  # old key can now be dropped
        assert decrypt_str(after) == "heal my mother"
    assert AuditLog.objects.filter(action=AuditLog.Action.KEY_ROTATION).exists()


def test_rotation_aborts_without_writing_when_a_row_cannot_be_decrypted() -> None:
    lost, current = Fernet.generate_key().decode(), Fernet.generate_key().decode()
    with override_settings(FIELD_ENCRYPTION_KEYS=[lost]):
        orphan = PrayerRequest.objects.create(request_text="old", consent=True)
    with override_settings(FIELD_ENCRYPTION_KEYS=[current]):
        ok = PrayerRequest.objects.create(request_text="new", consent=True)
        ok_before = raw_value(PrayerRequest, ok.pk, "request_text")
        orphan_before = raw_value(PrayerRequest, orphan.pk, "request_text")
        with pytest.raises(CommandError, match="cannot be decrypted"):
            call_command("rotate_encryption_keys", stdout=io.StringIO())
        assert raw_value(PrayerRequest, ok.pk, "request_text") == ok_before
        assert raw_value(PrayerRequest, orphan.pk, "request_text") == orphan_before


def test_undecryptable_placeholder_is_never_written_back() -> None:
    pr = PrayerRequest.objects.create(request_text="real text", consent=True)
    pr.request_text = DECRYPTION_FAILED
    with pytest.raises(ValueError, match="could not be decrypted"):
        pr.save()


# ------------------------------------------------------------------ I-4 data-subject requests
@pytest.fixture
def person_records() -> dict:
    return {
        "prayer": PrayerRequest.objects.create(request_text="pray for me", email=PERSON, consent=True),
        "contact": ContactMessage.objects.create(
            name="Pat", email=PERSON.upper(), subject="Hi", message="hello", consent=True
        ),
        "subscriber": Subscriber.objects.create(email=PERSON),
        "donation": Donation.objects.create(
            amount=Decimal("10.00"), currency="USD", donor_name="Pat", donor_email=PERSON, donor_phone="+211"
        ),
        "other": PrayerRequest.objects.create(request_text="not theirs", email=OTHER, consent=True),
    }


def test_export_person_returns_all_their_records_and_nothing_else(person_records: dict) -> None:
    data = json.loads(privacy.export_person(PERSON, actor="test"))
    assert data["prayer.PrayerRequest"][0]["request_text"] == "pray for me"
    assert data["contact.ContactMessage"][0]["message"] == "hello"  # matched case-insensitively
    assert data["giving.Donation"][0]["donor_name"] == "Pat"
    assert "not theirs" not in json.dumps(data)
    assert not any(k.endswith("_hash") for rows in data.values() for k in rows[0])
    log = AuditLog.objects.get(action=AuditLog.Action.PRIVACY_EXPORT)
    assert PERSON not in json.dumps(log.extra)


def test_erase_person_deletes_submissions_and_anonymises_donations(person_records: dict) -> None:
    result = privacy.erase_person(PERSON, actor="test")
    assert result["prayer.PrayerRequest"] == 1 and result["giving.Donation"] == 1
    assert not PrayerRequest.objects.filter(pk=person_records["prayer"].pk).exists()
    assert not ContactMessage.objects.exists() and not Subscriber.objects.exists()
    donation = Donation.objects.get(pk=person_records["donation"].pk)  # financial record kept
    assert donation.amount == Decimal("10.00")
    assert (donation.donor_name, donation.donor_email, donation.donor_phone, donation.donor_email_hash) == (
        "",
        "",
        "",
        "",
    )
    assert donation.is_anonymous
    assert PrayerRequest.objects.filter(pk=person_records["other"].pk).exists()
    assert PERSON not in json.dumps(AuditLog.objects.get(action=AuditLog.Action.PRIVACY_ERASE).extra)


def test_personal_data_command_requires_confirmation_for_erase(person_records: dict) -> None:
    out = io.StringIO()
    call_command("personal_data", "find", "--email", PERSON, stdout=out)
    assert "prayer.PrayerRequest: 1" in out.getvalue()
    with pytest.raises(CommandError, match="--yes"):
        call_command("personal_data", "erase", "--email", PERSON, stdout=io.StringIO())
    assert PrayerRequest.objects.filter(pk=person_records["prayer"].pk).exists()
    call_command("personal_data", "erase", "--email", PERSON, "--yes", stdout=io.StringIO())
    assert not PrayerRequest.objects.filter(pk=person_records["prayer"].pk).exists()


def test_personal_data_command_export(person_records: dict) -> None:
    out = io.StringIO()
    call_command("personal_data", "export", "--email", PERSON, stdout=out)
    assert "pray for me" in out.getvalue()


# ------------------------------------------------------------------ I-5 list views are audited
def test_viewing_a_sensitive_list_is_audit_logged_without_search_term(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    PrayerRequest.objects.create(request_text="x", consent=True)
    client = verified_client(make_staff(MEMBERSHIP))
    resp = client.get(f"{admin_prefix}prayer/prayerrequest/", {"q": PERSON, "status": "new"})
    assert resp.status_code == 200
    log = AuditLog.objects.filter(action=AuditLog.Action.VIEW, model="prayerrequest").latest("timestamp")
    assert log.extra["list"] is True and log.extra["query"] == {"status": "new"}
    assert PERSON not in json.dumps(log.extra)


# ------------------------------------------------------------------ I-7 decompression-bomb range
def test_image_between_one_and_two_times_pixel_limit_is_rejected() -> None:
    buf = io.BytesIO()
    Image.new("1", (7000, 7000)).save(buf, format="PNG")  # 49 MP > 40 MP limit, < 2x (no hard error)
    upload = SimpleUploadedFile("big.png", buf.getvalue(), content_type="image/png")
    with pytest.raises(ValidationError, match="could not be read"):
        validate_upload(upload, "gallery_photo")


def test_encryption_helpers_roundtrip() -> None:
    assert decrypt_str(encrypt_str("ok")) == "ok"
