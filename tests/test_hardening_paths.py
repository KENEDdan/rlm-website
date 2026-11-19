"""Phase J: edge paths of security-relevant code that the feature tests do not reach."""

from __future__ import annotations

import io
import time
from unittest import mock

import pytest
from django.core.management import call_command
from django.db import DatabaseError
from django.test import Client, override_settings

from accounts import twofactor
from core.crypto import blind_index
from events.models import Event
from prayer.models import PrayerRequest
from registrations.models import EventRegistration
from tests.conftest import PASSWORD
from tests.test_forms import event, reg_data  # noqa: F401 - fixture re-used
from tests.test_giving import EVENT, SECRET, gateway_on, signed  # noqa: F401 - fixture re-used

pytestmark = pytest.mark.django_db


# ------------------------------------------------------------------ 2FA pending-login window
def _password_step(client: Client, user, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    resp = client.post(f"{admin_prefix}account/login/", {"username": user.email, "password": PASSWORD})
    assert resp.status_code == 302


def test_pending_2fa_expires_after_ttl(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff()
    twofactor.get_or_create_unconfirmed_totp(user)
    _password_step(client, user, admin_prefix)
    later = time.time() + twofactor.PENDING_TTL_SECONDS + 1
    with mock.patch("accounts.twofactor.time.time", return_value=later):
        resp = client.get(f"{admin_prefix}account/2fa/setup/")
    assert resp.status_code == 302 and resp["Location"].endswith("/account/login/")


def test_pending_2fa_cleared_after_max_attempts(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    from django_otp.plugins.otp_totp.models import TOTPDevice

    user = make_staff()
    TOTPDevice.objects.create(user=user, name="t", confirmed=True)
    _password_step(client, user, admin_prefix)
    for _ in range(twofactor.MAX_ATTEMPTS):
        client.post(f"{admin_prefix}account/2fa/verify/", {"code": "000000"})
    resp = client.get(f"{admin_prefix}account/2fa/verify/")
    assert resp.status_code == 302 and resp["Location"].endswith("/account/login/")


def test_pending_2fa_cleared_when_user_deactivated(client: Client, make_staff, admin_prefix: str) -> None:  # type: ignore[no-untyped-def]
    user = make_staff()
    _password_step(client, user, admin_prefix)
    user.is_active = False
    user.save()
    resp = client.get(f"{admin_prefix}account/2fa/setup/")
    assert resp.status_code == 302 and resp["Location"].endswith("/account/login/")


def test_overlong_or_empty_codes_are_rejected_without_lookup(make_staff) -> None:  # type: ignore[no-untyped-def]
    user = make_staff()
    assert twofactor.verify_code(user, "") is None
    assert twofactor.verify_code(user, "1" * 17) is None


# ------------------------------------------------------------------ webhook edge cases
@override_settings(PAYMENT_WEBHOOK_SECRETS={"gateway": SECRET})
def test_webhook_rejects_missing_signature_oversized_and_malformed(client: Client, gateway_on) -> None:  # type: ignore[no-untyped-def]  # noqa: F811
    no_sig = client.post("/payments/webhook/gateway/", data=b"{}", content_type="application/json")
    assert no_sig.status_code == 400
    with mock.patch("giving.providers.hosted_gateway.MAX_BODY_BYTES", 10):
        assert signed(client, EVENT).status_code == 400
    assert signed(client, {"no": "id"}).status_code == 400  # signed but malformed


# ------------------------------------------------------------------ encrypted-field guards
def test_encrypted_fields_refuse_unsafe_lookups() -> None:
    with pytest.raises(NotImplementedError):
        list(PrayerRequest.objects.filter(request_text__icontains="x"))
    with pytest.raises(NotImplementedError):
        list(PrayerRequest.objects.filter(request_text="plaintext"))
    assert PrayerRequest.objects.filter(email="").count() == 0
    assert PrayerRequest.objects.filter(email__isnull=True).count() == 0


# ------------------------------------------------------------------ last seat race
def test_last_seat_taken_between_validation_and_save(client: Client, event: Event) -> None:  # noqa: F811
    event.capacity = 1
    event.save()

    def competitor_then_hash(value: str) -> str:
        # Simulates another visitor taking the last seat while this request is in flight.
        EventRegistration.objects.create(
            event=event, full_name="Other", email="other@example.test", attendees=1, consent=True
        )
        return blind_index(value)

    with mock.patch("events.views.blind_index", side_effect=competitor_then_hash):
        resp = client.post(f"/events/{event.slug}/register/", reg_data())
    assert resp.status_code == 200 and b"full" in resp.content.lower()
    assert EventRegistration.objects.filter(email_hash=blind_index("reg@example.test")).count() == 0


# ------------------------------------------------------------------ infrastructure
def test_healthz_reports_database_failure_without_details(client: Client) -> None:
    with mock.patch("core.views.connection.cursor", side_effect=DatabaseError("password=hunter2")):
        resp = client.get("/healthz/")
    assert resp.status_code == 503 and resp.json() == {"status": "error"}


def test_sync_roles_command_is_idempotent() -> None:
    out = io.StringIO()
    call_command("sync_roles", stdout=out)
    call_command("sync_roles", stdout=out)
    assert "Membership Administration" in out.getvalue()


# ------------------------------------------------------------------ seed_demo
def test_seed_demo_refuses_when_debug_is_off() -> None:
    from django.core.management import CommandError

    with override_settings(DEBUG=False), pytest.raises(CommandError, match="DEBUG"):
        call_command("seed_demo", stdout=io.StringIO())
    assert not Event.objects.filter(slug__startswith="demo-").exists()


def test_seed_demo_is_fake_idempotent_and_resettable() -> None:
    from giving.models import Donation
    from news.models import Post

    with override_settings(DEBUG=True):
        call_command("seed_demo", "--no-images", stdout=io.StringIO())
        counts = (Event.objects.count(), Post.objects.count(), PrayerRequest.objects.count())
        call_command("seed_demo", "--no-images", stdout=io.StringIO())
        assert (Event.objects.count(), Post.objects.count(), PrayerRequest.objects.count()) == counts
        assert all(p.email.endswith("@example.test") for p in PrayerRequest.objects.all())
        assert all(e.title.startswith("DEMO") for e in Event.objects.filter(slug__startswith="demo-"))
        call_command("seed_demo", "--reset", stdout=io.StringIO())
    assert not Event.objects.filter(slug__startswith="demo-").exists()
    assert not PrayerRequest.objects.exists() and not Donation.objects.exists()


def test_seed_demo_images_go_through_the_upload_pipeline(settings, tmp_path) -> None:  # type: ignore[no-untyped-def]
    from media_library.models import Photo

    settings.MEDIA_ROOT = tmp_path
    with override_settings(DEBUG=True):
        call_command("seed_demo", stdout=io.StringIO())
    photo = Photo.objects.first()
    assert photo is not None and photo.image.name.endswith(".jpg")
    assert (tmp_path / photo.image.name.replace(".jpg", "_w480.webp")).exists()


# ------------------------------------------------------------------ found while writing the admin guide
def test_cancelled_registrations_free_their_seats(event: Event) -> None:  # noqa: F811
    event.capacity = 2
    event.save()
    reg = EventRegistration.objects.create(
        event=event, full_name="A", email="a@example.test", attendees=2, consent=True
    )
    assert event.spots_left == 0 and not event.can_register
    reg.registration_status = EventRegistration.Status.CANCELLED
    reg.save()
    assert event.spots_left == 2 and event.can_register
    reg.registration_status = EventRegistration.Status.CONFIRMED
    reg.status = "handled"  # inbox status must NOT affect seats
    reg.save()
    assert event.spots_left == 0


def test_staff_can_regenerate_backup_codes_from_admin(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(superuser=True))
    page = client.get(admin_prefix)
    assert b"account/2fa/backup-codes/regenerate/" in page.content
    resp = client.post(f"{admin_prefix}account/2fa/backup-codes/regenerate/", follow=True)
    assert resp.status_code == 200 and len(resp.context["codes"]) == 10


# ------------------------------------------------------------------ container healthcheck
def test_healthcheck_uses_an_allowed_host_name() -> None:
    import importlib.util
    from pathlib import Path

    spec = importlib.util.spec_from_file_location("healthcheck", Path("docker/healthcheck.py"))
    module = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    spec.loader.exec_module(module)  # type: ignore[union-attr]
    assert module.host_header("rlm.example.org,www.rlm.example.org") == "rlm.example.org"
    assert module.host_header(".example.org") == "example.org"
    assert module.host_header("") == "localhost"
    with mock.patch.object(module.urllib.request, "urlopen", side_effect=OSError):
        assert module.main() == 1


# ------------------------------------------------------------------ staff-account admin (found by the dev audit)
def test_user_admin_is_read_only_even_for_superusers(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    """Accounts are managed only in the portal (re-auth, invite-only, limits, audit); the admin cannot bypass it."""
    from accounts.models import User

    target = make_staff()
    founder = verified_client(make_staff(superuser=True))
    assert founder.get(f"{admin_prefix}accounts/user/").status_code == 200
    assert founder.get(f"{admin_prefix}accounts/user/add/").status_code == 403
    resp = founder.post(
        f"{admin_prefix}accounts/user/add/",
        {"email": "new.staff@example.test", "full_name": "New", "password1": PASSWORD, "password2": PASSWORD},
    )
    assert resp.status_code == 403
    assert not User.objects.filter(email="new.staff@example.test").exists()
    resp = founder.post(
        f"{admin_prefix}accounts/user/{target.pk}/change/",
        {"email": target.email, "full_name": "Changed", "is_superuser": "on"},
    )
    target.refresh_from_db()
    assert resp.status_code in (200, 403) and not target.is_superuser and target.full_name == "Test Staff"
    assert (
        founder.post(f"{admin_prefix}accounts/user/{target.pk}/delete/", {"post": "yes"}).status_code == 403
    )
    assert User.objects.filter(pk=target.pk).exists()
    resp = founder.get(f"{admin_prefix}accounts/user/{target.pk}/password/", follow=True)
    assert b'name="password1"' not in resp.content  # no "set someone else's password" screen


def test_non_founder_cannot_open_user_admin(make_staff, verified_client, admin_prefix) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import MEMBERSHIP

    client = verified_client(make_staff(MEMBERSHIP))
    assert client.get(f"{admin_prefix}accounts/user/").status_code == 403
