from __future__ import annotations

from typing import Any

import pytest
from django.conf import settings
from django.contrib.auth.models import Group
from django.core.cache import cache
from django.test import Client
from django_otp.oath import TOTP
from django_otp.plugins.otp_totp.models import TOTPDevice

PASSWORD = "Str0ng-Test-Passw0rd!"


@pytest.fixture(autouse=True)
def _clear_cache() -> None:
    cache.clear()


@pytest.fixture
def admin_prefix() -> str:
    return "/" + settings.ADMIN_URL


def totp_now(device: TOTPDevice) -> str:
    return TOTP(device.bin_key, device.step, device.t0, device.digits, device.drift).token()


def format_token(token: int) -> str:
    return str(token).zfill(6)


@pytest.fixture
def make_staff(db: Any, django_user_model: Any):  # type: ignore[no-untyped-def]
    counter = {"n": 0}

    def _make(*groups: str, superuser: bool = False, branch: Any = None, department: Any = None, **kw: Any):  # type: ignore[no-untyped-def]
        counter["n"] += 1
        email = kw.pop("email", f"staff{counter['n']}@example.test")
        factory = (
            django_user_model.objects.create_superuser if superuser else django_user_model.objects.create_user
        )
        user = factory(email=email, password=PASSWORD, full_name="Test Staff", is_staff=True, **kw)
        if branch or department:
            user.branch, user.department = branch, department
            user.save()
        for name in groups:
            user.groups.add(Group.objects.get(name=name))
        return user

    return _make


@pytest.fixture
def verified_client(db: Any):  # type: ignore[no-untyped-def]
    """Return a function that logs a user in through the real password + TOTP flow."""

    def _login(user: Any) -> Client:
        client = Client()
        device = TOTPDevice.objects.filter(user=user, confirmed=True).first()
        if device is None:
            device = TOTPDevice.objects.create(user=user, name="test", confirmed=True)
        resp = client.post(
            "/" + settings.ADMIN_URL + "account/login/", {"username": user.email, "password": PASSWORD}
        )
        assert resp.status_code == 302, resp.content[:500]
        resp = client.post(
            "/" + settings.ADMIN_URL + "account/2fa/verify/", {"code": format_token(totp_now(device))}
        )
        assert resp.status_code == 302, resp.content[:500]
        return client

    return _login
