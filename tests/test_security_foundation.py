"""Encryption, audit log immutability, headers, logging scrubbing, honeypot/Turnstile, uploads."""

from __future__ import annotations

import io
import logging
from unittest import mock

import pytest
from cryptography.fernet import Fernet
from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection, transaction
from django.db.utils import DatabaseError
from django.test import Client, RequestFactory, override_settings
from PIL import Image

from audit.models import AuditLog
from audit.services import log_event
from core import crypto
from core.fields import EncryptedTextField
from core.forms import ProtectedFormMixin
from core.logging import PIIScrubFilter, scrub_data, sentry_before_send
from core.upload_policy import validate_upload
from core.uploads import (
    SafeImageField,
    rendition_name,
    sanitise_image,
)


def validate_image_upload(file):  # type: ignore[no-untyped-def]
    validate_upload(file, "gallery_photo")


def validate_pdf_upload(file):  # type: ignore[no-untyped-def]
    validate_upload(file, "public_document")


@pytest.fixture(autouse=True)
def _reset_fernet_cache() -> None:
    crypto._multifernet.cache_clear()
    yield
    crypto._multifernet.cache_clear()


# ---------------------------------------------------------------- encryption
def test_encrypt_round_trip_and_ciphertext_differs() -> None:
    token = crypto.encrypt_str("Please pray for my family")
    assert "pray" not in token
    assert crypto.is_encrypted_token(token)
    assert crypto.decrypt_str(token) == "Please pray for my family"
    assert crypto.encrypt_str("same") != crypto.encrypt_str("same")  # non-deterministic


def test_field_prep_and_from_db() -> None:
    field = EncryptedTextField()
    stored = field.get_prep_value("secret text")
    assert stored != "secret text" and crypto.is_encrypted_token(stored)
    assert field.from_db_value(stored, None, connection) == "secret text"
    assert field.get_prep_value("") == ""
    assert field.get_prep_value(None) is None


def test_key_rotation_old_tokens_still_decrypt(settings) -> None:  # type: ignore[no-untyped-def]
    old_key = settings.FIELD_ENCRYPTION_KEYS[0]
    token_old = crypto.encrypt_str("rotate me")
    new_key = Fernet.generate_key().decode()
    settings.FIELD_ENCRYPTION_KEYS = [new_key, old_key]
    crypto._multifernet.cache_clear()
    assert crypto.decrypt_str(token_old) == "rotate me"
    rotated = crypto.rotate_token(token_old)
    settings.FIELD_ENCRYPTION_KEYS = [new_key]  # old key retired
    crypto._multifernet.cache_clear()
    assert crypto.decrypt_str(rotated) == "rotate me"
    assert crypto.decrypt_str(token_old) == crypto.DECRYPTION_FAILED


def test_blind_index_is_normalised_and_keyed(settings) -> None:  # type: ignore[no-untyped-def]
    a = crypto.blind_index(" Person@Example.org ")
    assert a == crypto.blind_index("person@example.org")
    assert "person" not in a and len(a) == 64
    settings.BLIND_INDEX_KEY = "different"
    assert crypto.blind_index("person@example.org") != a
    assert crypto.blind_index("") == ""


def test_encrypted_field_rejects_unsupported_lookups() -> None:
    field = EncryptedTextField()
    with pytest.raises(NotImplementedError):
        field.get_lookup("icontains")


# ---------------------------------------------------------------- audit log
@pytest.mark.django_db
def test_audit_log_is_append_only() -> None:
    entry = log_event(AuditLog.Action.EXPORT, actor_email="founder@example.test")
    entry.action = "view"
    with pytest.raises(PermissionError):
        entry.save()
    with pytest.raises(PermissionError):
        entry.delete()
    with pytest.raises(PermissionError):
        AuditLog.objects.all().update(action="x")
    with pytest.raises(PermissionError):
        AuditLog.objects.all().delete()


@pytest.mark.django_db
def test_audit_log_database_trigger_blocks_raw_sql() -> None:
    entry = log_event(AuditLog.Action.EXPORT)
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
        cur.execute("UPDATE audit_auditlog SET action = 'x' WHERE id = %s", [entry.pk])
    with pytest.raises(DatabaseError), transaction.atomic(), connection.cursor() as cur:
        cur.execute("DELETE FROM audit_auditlog WHERE id = %s", [entry.pk])
    assert AuditLog.objects.get(pk=entry.pk).action == "export"


@pytest.mark.django_db
def test_audit_entry_records_request_metadata(rf: RequestFactory) -> None:
    request = rf.get("/", HTTP_USER_AGENT="pytest", REMOTE_ADDR="203.0.113.9")
    entry = log_event(AuditLog.Action.VIEW, request=request)
    assert entry.ip_address == "203.0.113.9" and entry.user_agent == "pytest"


# ---------------------------------------------------------------- headers
@pytest.mark.django_db
def test_security_headers_present(client: Client) -> None:
    resp = client.get("/healthz/")
    assert resp.status_code == 200
    csp = resp["Content-Security-Policy"]
    assert "default-src 'self'" in csp and "frame-ancestors 'none'" in csp and "object-src 'none'" in csp
    assert "unsafe-inline" not in csp.split("script-src")[1].split(";")[0]
    assert resp["X-Frame-Options"] == "DENY"
    assert resp["X-Content-Type-Options"] == "nosniff"
    assert resp["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in resp["Permissions-Policy"]


@pytest.mark.django_db
def test_admin_responses_are_not_cached(client: Client, admin_prefix: str) -> None:
    resp = client.get(admin_prefix + "account/login/")
    assert "no-store" in resp["Cache-Control"]
    assert "noindex" in resp["X-Robots-Tag"]


def test_production_settings_are_hardened(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import importlib

    prod = importlib.import_module("config.settings.prod")
    assert prod.DEBUG is False
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SECURE_HSTS_SECONDS >= 31536000 and prod.SECURE_HSTS_PRELOAD
    assert prod.SESSION_COOKIE_SECURE and prod.CSRF_COOKIE_SECURE
    assert prod.SESSION_COOKIE_HTTPONLY and prod.SESSION_COOKIE_NAME.startswith("__Host-")


@override_settings(TRUST_PROXY_IP_HEADER=False)
@pytest.mark.django_db
def test_spoofed_ip_header_ignored_unless_trusted(rf: RequestFactory) -> None:
    from core.middleware import RealIPMiddleware

    request = rf.get("/", HTTP_X_REAL_IP="198.51.100.1", REMOTE_ADDR="10.0.0.2")
    RealIPMiddleware(lambda r: r)(request)
    assert request.META["REMOTE_ADDR"] == "10.0.0.2"
    with override_settings(TRUST_PROXY_IP_HEADER=True):
        request = rf.get("/", HTTP_X_REAL_IP="198.51.100.1", REMOTE_ADDR="10.0.0.2")
        RealIPMiddleware(lambda r: r)(request)
        assert request.META["REMOTE_ADDR"] == "198.51.100.1"
        bad = rf.get("/", HTTP_X_REAL_IP="not-an-ip", REMOTE_ADDR="10.0.0.2")
        RealIPMiddleware(lambda r: r)(bad)
        assert bad.META["REMOTE_ADDR"] == "10.0.0.2"


# ---------------------------------------------------------------- error pages
@pytest.mark.django_db
def test_404_page_is_generic(client: Client) -> None:
    resp = client.get("/does-not-exist/")
    assert resp.status_code == 404
    assert b"Page not found" in resp.content
    assert b"Traceback" not in resp.content


def test_500_page_renders_without_details(rf: RequestFactory) -> None:
    from core.views import error_500

    resp = error_500(rf.get("/"))
    assert resp.status_code == 500 and b"Something went wrong" in resp.content


# ---------------------------------------------------------------- logging
def test_pii_scrub_filter_masks_email_phone_and_ciphertext() -> None:
    record = logging.LogRecord(
        "x", logging.INFO, __file__, 1, "user %s phone %s", ("a.b@example.org", "+211 900 000 001"), None
    )
    PIIScrubFilter().filter(record)
    msg = record.getMessage()
    assert "example.org" not in msg and "912" not in msg and "[email]" in msg and "[phone]" in msg


def test_sentry_before_send_strips_request_body_and_user() -> None:
    event = {
        "request": {
            "data": {"request_text": "secret"},
            "cookies": {"a": "b"},
            "headers": {"Cookie": "x", "User-Agent": "ua"},
        },
        "user": {"email": "x@example.org"},
        "extra": {"email": "y@example.org", "note": "call +211900000002"},
    }
    out = sentry_before_send(event, {})
    assert "data" not in out["request"] and "cookies" not in out["request"]
    assert out["request"]["headers"] == {"User-Agent": "ua"}
    assert "user" not in out
    assert out["extra"]["email"] == "[scrubbed]" and "[phone]" in out["extra"]["note"]
    assert scrub_data(["a@b.example"]) == ["[email]"]


# ---------------------------------------------------------------- honeypot / Turnstile
class DemoForm(ProtectedFormMixin):
    name = forms.CharField()


def test_honeypot_rejects_bots(rf: RequestFactory) -> None:
    form = DemoForm({"name": "x", "website": "http://spam"}, request=rf.post("/"))
    assert not form.is_valid()
    assert DemoForm({"name": "x"}, request=rf.post("/")).is_valid()


@override_settings(TURNSTILE_ENABLED=True, TURNSTILE_SECRET_KEY="test-secret")
def test_turnstile_required_when_enabled(rf: RequestFactory) -> None:
    assert not DemoForm({"name": "x"}, request=rf.post("/")).is_valid()  # no token
    fake = mock.MagicMock()
    fake.__enter__.return_value.read.return_value = b'{"success": true}'
    with mock.patch("core.turnstile.urllib.request.urlopen", return_value=fake) as called:
        assert DemoForm({"name": "x", "cf-turnstile-response": "tok"}, request=rf.post("/")).is_valid()
        assert called.call_args.args[0].full_url.startswith("https://challenges.cloudflare.com/")
    with mock.patch("core.turnstile.urllib.request.urlopen", side_effect=OSError):
        assert not DemoForm({"name": "x", "cf-turnstile-response": "tok"}, request=rf.post("/")).is_valid()


# ---------------------------------------------------------------- uploads
def _jpeg_with_gps() -> bytes:
    img = Image.new("RGB", (2000, 1200), (240, 101, 42))
    exif = Image.Exif()
    exif[0x8825] = {1: "N", 2: (4.0, 51.0, 0.0)}  # GPSInfo: latitude
    exif[0x010F] = "SecretCam"  # Make
    buf = io.BytesIO()
    img.save(buf, format="JPEG", exif=exif)
    return buf.getvalue()


def test_image_validator_rejects_spoofed_content() -> None:
    fake = SimpleUploadedFile("evil.jpg", b"<?php system($_GET['c']); ?>", content_type="image/jpeg")
    with pytest.raises(ValidationError):
        validate_image_upload(fake)
    svg = SimpleUploadedFile("x.svg", b"<svg onload=alert(1)>", content_type="image/svg+xml")
    with pytest.raises(ValidationError):
        validate_image_upload(svg)


def test_image_validator_enforces_size_cap(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    import dataclasses

    from core import upload_policy

    small = dataclasses.replace(upload_policy.POLICIES["gallery_photo"], max_bytes=1024)
    monkeypatch.setitem(upload_policy.POLICIES, "gallery_photo", small)
    big = SimpleUploadedFile("big.jpg", _jpeg_with_gps(), content_type="image/jpeg")
    with pytest.raises(ValidationError, match="too large"):
        validate_image_upload(big)


def test_sanitise_strips_exif_and_gps() -> None:
    raw = _jpeg_with_gps()
    assert b"SecretCam" in raw
    data, ext, _img = sanitise_image(SimpleUploadedFile("a.jpg", raw))
    assert ext == "jpg" and b"SecretCam" not in data
    with Image.open(io.BytesIO(data)) as clean:
        assert not clean.getexif()


@pytest.mark.django_db
def test_safe_image_field_randomises_name_and_writes_renditions(tmp_path, settings) -> None:  # type: ignore[no-untyped-def]
    settings.MEDIA_ROOT = tmp_path
    from branches.models import Branch, Country

    country = Country.objects.create(name="Testland", code="TL")
    branch = Branch(country=country, name="Test", slug="test")
    branch.image = SimpleUploadedFile("my-family-photo.jpg", _jpeg_with_gps(), content_type="image/jpeg")
    branch.full_clean()
    branch.save()
    assert "my-family-photo" not in branch.image.name
    assert branch.image.name.startswith("branches/") and branch.image.name.endswith(".jpg")
    for w in (480, 960, 1600):
        assert (tmp_path / rendition_name(branch.image.name, w)).exists()
    assert isinstance(Branch._meta.get_field("image"), SafeImageField)


def test_pdf_validator() -> None:
    validate_pdf_upload(
        SimpleUploadedFile("r.pdf", b"%PDF-1.4\n%\xe2\xe3\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF")
    )
    with pytest.raises(ValidationError):
        validate_pdf_upload(SimpleUploadedFile("r.pdf", b"MZ\x90\x00 not a pdf"))
    with pytest.raises(ValidationError):
        validate_pdf_upload(SimpleUploadedFile("r.exe", b"%PDF-1.4"))
