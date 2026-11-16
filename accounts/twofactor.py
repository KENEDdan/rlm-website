"""Mandatory TOTP two-factor flow for staff.

Password success does NOT log the user in. It stores a short-lived "pending" marker in the session.
The user is logged in only after a valid TOTP (or one-time backup) code, so an attacker with only a password
never gets an authenticated session.
"""

from __future__ import annotations

import secrets
import time
from typing import Any

from django.contrib.auth import get_user_model
from django.http import HttpRequest
from django_otp.plugins.otp_static.models import StaticDevice, StaticToken
from django_otp.plugins.otp_totp.models import TOTPDevice

PENDING_KEY = "2fa_pending"
PENDING_TTL_SECONDS = 600
MAX_ATTEMPTS = 5
BACKUP_CODE_COUNT = 10


def start_pending(request: HttpRequest, user: Any, backend: str) -> None:
    request.session.cycle_key()
    request.session[PENDING_KEY] = {
        "uid": user.pk,
        "backend": backend,
        "ts": int(time.time()),
        "attempts": 0,
    }


def clear_pending(request: HttpRequest) -> None:
    request.session.pop(PENDING_KEY, None)


def get_pending_user(request: HttpRequest) -> tuple[Any, str] | tuple[None, None]:
    data = request.session.get(PENDING_KEY)
    if not data:
        return None, None
    if time.time() - data.get("ts", 0) > PENDING_TTL_SECONDS or data.get("attempts", 0) >= MAX_ATTEMPTS:
        clear_pending(request)
        return None, None
    user = get_user_model().objects.filter(pk=data["uid"], is_active=True, is_staff=True).first()
    if user is None:
        clear_pending(request)
        return None, None
    return user, data["backend"]


def record_failed_attempt(request: HttpRequest) -> int:
    data = request.session.get(PENDING_KEY) or {}
    data["attempts"] = data.get("attempts", 0) + 1
    request.session[PENDING_KEY] = data
    return data["attempts"]


def confirmed_totp(user: Any) -> TOTPDevice | None:
    return TOTPDevice.objects.filter(user=user, confirmed=True).first()


def get_or_create_unconfirmed_totp(user: Any) -> TOTPDevice:
    device = TOTPDevice.objects.filter(user=user, confirmed=False).first()
    if device is None:
        device = TOTPDevice.objects.create(user=user, name="Authenticator app", confirmed=False)
    return device


def verify_code(user: Any, code: str) -> Any:
    """Return the device that accepted ``code`` (TOTP first, then backup codes), else None."""
    code = (code or "").strip().replace(" ", "").lower()
    if not code or len(code) > 16:
        return None
    for device in TOTPDevice.objects.filter(user=user, confirmed=True):
        if code.isdigit() and device.verify_token(code):
            return device
    for device in StaticDevice.objects.filter(user=user, confirmed=True):
        if device.verify_token(code):
            return device
    return None


def regenerate_backup_codes(user: Any) -> list[str]:
    device, _ = StaticDevice.objects.get_or_create(
        user=user, name="Backup codes", defaults={"confirmed": True}
    )
    device.token_set.all().delete()
    codes = [secrets.token_hex(4) for _ in range(BACKUP_CODE_COUNT)]
    StaticToken.objects.bulk_create([StaticToken(device=device, token=c) for c in codes])
    return codes


def reset_two_factor(user: Any) -> None:
    TOTPDevice.objects.filter(user=user).delete()
    StaticDevice.objects.filter(user=user).delete()
