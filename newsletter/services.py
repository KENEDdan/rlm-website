"""Double opt-in newsletter. Tokens are signed (HMAC with SECRET_KEY), so nothing extra is stored."""

from __future__ import annotations

from django.core import signing
from django.db import transaction
from django.utils import timezone

from core.crypto import blind_index

from .models import Subscriber

CONFIRM_SALT = "newsletter.confirm"
UNSUBSCRIBE_SALT = "newsletter.unsubscribe"
CONFIRM_MAX_AGE = 60 * 60 * 24 * 7  # 7 days


def make_confirm_token(sub: Subscriber) -> str:
    return signing.TimestampSigner(salt=CONFIRM_SALT).sign(str(sub.pk))


def make_unsubscribe_token(sub: Subscriber) -> str:
    return signing.Signer(salt=UNSUBSCRIBE_SALT).sign(f"{sub.pk}:{sub.email_hash[:16]}")


def subscribe(email: str, name: str = "") -> Subscriber | None:
    """Create or refresh a pending subscription. Returns the subscriber that needs a confirmation
    email, or None if they are already confirmed (the caller shows the same message either way)."""
    from .tasks import send_confirmation

    existing = Subscriber.objects.filter(email_hash=blind_index(email)).first()
    if existing and existing.status == Subscriber.Status.CONFIRMED:
        return None
    sub = existing or Subscriber(email=email)
    sub.name = name or sub.name
    sub.status = Subscriber.Status.PENDING
    sub.save()
    transaction.on_commit(lambda: send_confirmation.delay(sub.pk))
    return sub


def confirm(token: str) -> Subscriber | None:
    try:
        pk = signing.TimestampSigner(salt=CONFIRM_SALT).unsign(token, max_age=CONFIRM_MAX_AGE)
    except signing.BadSignature:
        return None
    sub = Subscriber.objects.filter(pk=pk).first()
    if sub is None or sub.status == Subscriber.Status.UNSUBSCRIBED:
        return None
    if sub.status != Subscriber.Status.CONFIRMED:
        sub.status = Subscriber.Status.CONFIRMED
        sub.confirmed_at = timezone.now()
        sub.save(update_fields=["status", "confirmed_at", "updated_at"])
    return sub


def subscriber_from_unsubscribe_token(token: str) -> Subscriber | None:
    try:
        value = signing.Signer(salt=UNSUBSCRIBE_SALT).unsign(token)
        pk, hash_prefix = value.split(":", 1)
    except (signing.BadSignature, ValueError):
        return None
    sub = Subscriber.objects.filter(pk=pk).first()
    if sub is None or sub.email_hash[:16] != hash_prefix:
        return None
    return sub


def unsubscribe(sub: Subscriber) -> None:
    sub.status = Subscriber.Status.UNSUBSCRIBED
    sub.unsubscribed_at = timezone.now()
    sub.save(update_fields=["status", "unsubscribed_at", "updated_at"])
