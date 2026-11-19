"""Phase F: public forms: validation, encryption at rest, notifications, throttling, HTMX, admin export."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.core import mail
from django.db import connection
from django.test import Client, override_settings
from django.utils import timezone

from audit.models import AuditLog
from branches.models import Branch
from contact.models import ContactMessage
from core.crypto import blind_index, is_encrypted_token
from core.models import SiteSettings
from core.tasks import purge_expired_submissions
from events.models import Event
from newsletter import services as nl
from newsletter.models import Subscriber
from prayer.models import PrayerRequest
from registrations.models import EventRegistration, VolunteerApplication

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _run_on_commit(monkeypatch):  # type: ignore[no-untyped-def]
    """Emails are queued with transaction.on_commit; tests run inside a transaction, so run them now."""
    monkeypatch.setattr("django.db.transaction.on_commit", lambda func, using=None, robust=False: func())


SECRET_PRAYER = "Please pray for my brother who is very sick"  # pragma: allowlist secret


@pytest.fixture(autouse=True)
def _notification_address() -> None:
    s = SiteSettings.get()
    s.notification_email = "office@example.test"
    s.save()


def raw_value(model, pk: int, column: str) -> str:  # type: ignore[no-untyped-def]
    with connection.cursor() as cur:
        cur.execute(
            f'SELECT "{column}" FROM "{model._meta.db_table}" WHERE id = %s',  # noqa: S608 - test-only constants
            [pk],
        )
        return cur.fetchone()[0]


def prayer_data(**kw: object) -> dict:
    data = {
        "request_text": SECRET_PRAYER,
        "keep_confidential": "on",
        "name": "Mary Example",
        "email": "mary@example.test",
        "consent": "on",
    }
    data.update(kw)
    return data


# ------------------------------------------------------------------ prayer
def test_prayer_request_is_encrypted_at_rest(client: Client) -> None:
    resp = client.post("/prayer/", prayer_data())
    assert resp.status_code == 302
    pr = PrayerRequest.objects.get()
    assert pr.request_text == SECRET_PRAYER  # decrypts transparently
    for column, plain in [
        ("request_text", SECRET_PRAYER),
        ("name", "Mary Example"),
        ("email", "mary@example.test"),
    ]:
        stored = raw_value(PrayerRequest, pr.pk, column)
        assert plain not in stored and is_encrypted_token(stored), column
    assert pr.email_hash == blind_index("MARY@example.test")


def test_prayer_alert_email_has_no_sensitive_content(client: Client) -> None:
    client.post("/prayer/", prayer_data())
    alert = next(m for m in mail.outbox if m.to == ["office@example.test"])
    ack = next(m for m in mail.outbox if m.to == ["mary@example.test"])
    for message in (alert, ack):
        assert SECRET_PRAYER not in message.body and "brother" not in message.body
        assert "Mary" not in message.body
    assert "/test-portal/prayer/prayerrequest/" in alert.body


def test_prayer_is_anonymous_by_default_and_contact_needs_details(client: Client) -> None:
    assert client.post("/prayer/", {"request_text": "pray", "consent": "on"}).status_code == 302
    resp = client.post("/prayer/", {"request_text": "pray", "consent": "on", "wants_contact": "on"})
    assert resp.status_code == 200 and b"so we can contact you" in resp.content


def test_consent_required(client: Client) -> None:
    resp = client.post("/prayer/", prayer_data(consent=""))
    assert resp.status_code == 200 and not PrayerRequest.objects.exists()


def test_honeypot_blocks_submission(client: Client) -> None:
    resp = client.post("/prayer/", prayer_data(website="http://spam.example"))
    assert resp.status_code == 200 and not PrayerRequest.objects.exists()


def test_length_limits(client: Client) -> None:
    resp = client.post("/prayer/", prayer_data(request_text="x" * 5000))
    assert resp.status_code == 200 and not PrayerRequest.objects.exists()


@override_settings(FORM_RATE="2/h")
def test_forms_are_rate_limited(client: Client) -> None:
    codes = [client.post("/prayer/", prayer_data()).status_code for _ in range(4)]
    assert codes[:2] == [302, 302] and 429 in codes[2:]
    assert PrayerRequest.objects.count() == 2


def test_htmx_returns_partial(client: Client) -> None:
    resp = client.post("/prayer/", prayer_data(), HTTP_HX_REQUEST="true")
    assert resp.status_code == 200 and b"<html" not in resp.content and b"received" in resp.content
    bad = client.post("/prayer/", prayer_data(request_text=""), HTTP_HX_REQUEST="true")
    assert b'id="prayer-form"' in bad.content and b"<html" not in bad.content


def test_forms_require_csrf() -> None:
    client = Client(enforce_csrf_checks=True)
    assert client.post("/prayer/", prayer_data()).status_code == 403


# ------------------------------------------------------------------ volunteer
def volunteer_data(**kw: object) -> dict:
    data = {
        "full_name": "John Example",
        "email": "john@example.test",
        "phone": "+211 900 000 001",
        "country": "South Sudan",
        "location": "Juba",
        "branch": Branch.objects.get(slug="juba").pk,
        "church_affiliation": "Example Church",
        "interests": ["youth", "media"],
        "availability": "weekends",
        "testimony": "My private testimony",
        "consent": "on",
    }
    data.update(kw)
    return data


def test_volunteer_application_encrypted_and_acknowledged(client: Client) -> None:
    assert client.post("/get-involved/", volunteer_data()).status_code == 302
    v = VolunteerApplication.objects.get()
    assert v.interests == ["youth", "media"] and v.consent
    for column in ("full_name", "email", "phone", "church_affiliation", "testimony"):
        assert is_encrypted_token(raw_value(VolunteerApplication, v.pk, column)), column
    assert {tuple(m.to) for m in mail.outbox} == {("office@example.test",), ("john@example.test",)}
    assert all("testimony" not in m.body.lower() for m in mail.outbox)


def test_volunteer_validation(client: Client) -> None:
    resp = client.post(
        "/get-involved/", volunteer_data(phone="call me", email="not-an-email", interests=["bogus"])
    )
    assert resp.status_code == 200 and not VolunteerApplication.objects.exists()


# ------------------------------------------------------------------ contact
def test_contact_message(client: Client) -> None:
    data = {
        "name": "Ann",
        "email": "ann@example.test",
        "topic": "general",
        "subject": "Hello",
        "message": "A question",
        "consent": "on",
    }
    assert client.post("/contact/", data).status_code == 302
    msg = ContactMessage.objects.get()
    assert is_encrypted_token(raw_value(ContactMessage, msg.pk, "message"))
    assert is_encrypted_token(raw_value(ContactMessage, msg.pk, "subject"))


# ------------------------------------------------------------------ events
@pytest.fixture
def event() -> Event:
    start = timezone.now() + timedelta(days=10)
    return Event.objects.create(
        title="Youth Conference",
        slug="youth-conf",
        summary="x",
        start=start,
        end=start + timedelta(hours=5),
        is_published=True,
        registration_open=True,
        capacity=3,
    )


def reg_data(**kw: object) -> dict:
    data = {"full_name": "Reg One", "email": "reg@example.test", "attendees": 1, "consent": "on"}
    data.update(kw)
    return data


def test_event_registration_and_confirmation_email(client: Client, event: Event) -> None:
    resp = client.post(f"/events/{event.slug}/register/", reg_data())
    assert resp.status_code == 302 and resp["Location"] == event.get_absolute_url()
    reg = EventRegistration.objects.get()
    assert is_encrypted_token(raw_value(EventRegistration, reg.pk, "full_name"))
    ack = next(m for m in mail.outbox if m.to == ["reg@example.test"])
    assert "Youth Conference" in ack.subject


def test_event_registration_duplicate_prevented(client: Client, event: Event) -> None:
    client.post(f"/events/{event.slug}/register/", reg_data())
    resp = client.post(f"/events/{event.slug}/register/", reg_data(email="REG@example.test"))
    assert resp.status_code == 302  # same message, no enumeration
    assert EventRegistration.objects.count() == 1


def test_event_capacity_enforced(client: Client, event: Event) -> None:
    client.post(f"/events/{event.slug}/register/", reg_data(attendees=2))
    resp = client.post(f"/events/{event.slug}/register/", reg_data(email="b@example.test", attendees=2))
    assert resp.status_code == 200 and b"Only 1 place" in resp.content
    client.post(f"/events/{event.slug}/register/", reg_data(email="c@example.test", attendees=1))
    event.refresh_from_db()
    assert event.spots_left == 0 and not event.can_register
    closed = client.get(f"/events/{event.slug}/register/")
    assert b"closed or the event is full" in closed.content


def test_registration_closed_event(client: Client, event: Event) -> None:
    event.registration_open = False
    event.save()
    client.post(f"/events/{event.slug}/register/", reg_data())
    assert not EventRegistration.objects.exists()


def test_unpublished_event_registration_404(client: Client, event: Event) -> None:
    event.is_published = False
    event.save()
    assert client.get(f"/events/{event.slug}/register/").status_code == 404


# ------------------------------------------------------------------ newsletter
def test_newsletter_double_opt_in_and_unsubscribe(client: Client) -> None:
    resp = client.post("/newsletter/subscribe/", {"email": "sub@example.test", "consent": "on"})
    assert resp.status_code == 200
    sub = Subscriber.objects.get()
    assert sub.status == "pending" and is_encrypted_token(raw_value(Subscriber, sub.pk, "email"))
    email = mail.outbox[-1]
    assert email.to == ["sub@example.test"] and "List-Unsubscribe" in email.extra_headers
    confirm_url = next(line for line in email.body.splitlines() if "/newsletter/confirm/" in line).strip()
    assert client.get(confirm_url.replace("http://localhost:8010", "")).status_code == 200
    sub.refresh_from_db()
    assert sub.status == "confirmed"
    unsub = "/newsletter/unsubscribe/" + nl.make_unsubscribe_token(sub) + "/"
    assert client.get(unsub).status_code == 200
    sub.refresh_from_db()
    assert sub.status == "confirmed"  # GET alone never unsubscribes (link scanners)
    client.post(unsub)
    sub.refresh_from_db()
    assert sub.status == "unsubscribed"


def test_newsletter_no_enumeration_and_bad_tokens(client: Client) -> None:
    first = client.post("/newsletter/subscribe/", {"email": "x@example.test", "consent": "on"}).content
    sub = Subscriber.objects.get()
    nl.confirm(nl.make_confirm_token(sub))
    second = client.post("/newsletter/subscribe/", {"email": "x@example.test", "consent": "on"}).content
    assert first == second or b"check your inbox" in second
    assert client.get("/newsletter/confirm/forged/").status_code == 400
    assert client.get("/newsletter/unsubscribe/forged:token/").status_code == 400


# ------------------------------------------------------------------ admin: export, handled, retention
def test_csv_export_permission_gated_and_audited(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import MEDIA, MEMBERSHIP

    PrayerRequest.objects.create(request_text='=HYPERLINK("http://evil")', consent=True)
    pr = PrayerRequest.objects.get()
    secretary = verified_client(make_staff(MEMBERSHIP))
    resp = secretary.post(
        "/test-portal/prayer/prayerrequest/", {"action": "export_csv", "_selected_action": [pr.pk]}
    )
    assert resp.status_code == 200 and resp["Content-Type"].startswith("text/csv")
    body = b"".join(resp.streaming_content).decode()
    assert "'=HYPERLINK" in body  # CSV/formula injection neutralised
    assert AuditLog.objects.filter(action="export", model="prayerrequest").exists()
    media = verified_client(make_staff(MEDIA))
    assert (
        media.post(
            "/test-portal/prayer/prayerrequest/", {"action": "export_csv", "_selected_action": [pr.pk]}
        ).status_code
        == 403
    )


def test_viewing_sensitive_record_is_audited(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import MEMBERSHIP

    pr = PrayerRequest.objects.create(request_text="secret", consent=True)
    client = verified_client(make_staff(MEMBERSHIP))
    assert client.get(f"/test-portal/prayer/prayerrequest/{pr.pk}/change/").status_code == 200
    entry = AuditLog.objects.get(action="view", model="prayerrequest")
    assert entry.object_id == str(pr.pk) and "secret" not in entry.object_repr


def test_mark_handled_action(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import MEMBERSHIP

    user = make_staff(MEMBERSHIP)
    pr = PrayerRequest.objects.create(request_text="x", consent=True)
    client = verified_client(user)
    client.post("/test-portal/prayer/prayerrequest/", {"action": "mark_handled", "_selected_action": [pr.pk]})
    pr.refresh_from_db()
    assert pr.status == "handled" and pr.handled_by == user


def test_admin_email_search_uses_blind_index(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    from accounts.roles import MEMBERSHIP

    PrayerRequest.objects.create(request_text="a", email="find.me@example.test", consent=True)
    PrayerRequest.objects.create(request_text="b", email="other@example.test", consent=True)
    client = verified_client(make_staff(MEMBERSHIP))
    resp = client.get("/test-portal/prayer/prayerrequest/", {"q": "Find.Me@example.test"})
    assert b"1 result" in resp.content


def test_retention_purge() -> None:
    old = PrayerRequest.objects.create(request_text="old", consent=True)
    new = PrayerRequest.objects.create(request_text="new", consent=True)
    PrayerRequest.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=400))
    result = purge_expired_submissions()
    assert result["prayer.PrayerRequest"] == 1
    assert list(PrayerRequest.objects.values_list("pk", flat=True)) == [new.pk]
    assert AuditLog.objects.filter(action="purge").exists()
    s = SiteSettings.get()
    s.retention_prayer_days = 0
    s.save()
    PrayerRequest.objects.filter(pk=new.pk).update(created_at=timezone.now() - timedelta(days=4000))
    assert purge_expired_submissions().get("prayer.PrayerRequest") is None


def test_public_cannot_add_submissions_in_admin(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(superuser=True))
    assert client.get("/test-portal/prayer/prayerrequest/add/").status_code == 403
