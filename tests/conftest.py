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
    """Create a staff user the way the Super Admin would (a sanctioned account change).

    Department groups also create the matching department membership; pass ``heads={"finance"}`` to make
    the user head of those departments, or ``members={"media"}`` for a membership without the group.
    ``scoped={"membership": juba}`` makes that assignment single-branch (D-026).
    """
    from accounts.guard import sanctioned
    from accounts.roles import DEPARTMENTS
    from portal.models import Department, DepartmentMembership

    code_for = {name: code for code, name in DEPARTMENTS}
    counter = {"n": 0}

    def _make(*groups: str, superuser: bool = False, branch: Any = None, heads: Any = (), members: Any = (), scoped: Any = None, **kw: Any):  # type: ignore[no-untyped-def]
        counter["n"] += 1
        email = kw.pop("email", f"staff{counter['n']}@example.test")
        factory = (
            django_user_model.objects.create_superuser if superuser else django_user_model.objects.create_user
        )
        with sanctioned("test:fixture"):
            user = factory(email=email, password=PASSWORD, full_name="Test Staff", is_staff=True, **kw)
            if branch:
                user.branch = branch
                user.save()
            codes = {code_for[g] for g in groups if g in code_for} | set(heads) | set(members)
            for name in groups:
                user.groups.add(Group.objects.get(name=name))
            for code in codes:
                DepartmentMembership.objects.create(
                    user=user,
                    department=Department.objects.get(code=code),
                    is_head=code in set(heads),
                    branch=(scoped or {}).get(code),
                )
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
        # A second sign-in by the same user within one 30-second step would reuse the same code, which
        # django-otp correctly refuses (replay protection). Tests forget the last-used step instead.
        TOTPDevice.objects.filter(pk=device.pk).update(
            last_t=-1, throttling_failure_count=0, throttling_failure_timestamp=None
        )
        device.refresh_from_db()
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


@pytest.fixture
def reauth():  # type: ignore[no-untyped-def]
    """Confirm identity again (password + fresh TOTP) in an already signed-in test client."""

    def _reauth(client: Client, user: Any) -> None:
        TOTPDevice.objects.filter(user=user).update(
            last_t=-1, throttling_failure_count=0, throttling_failure_timestamp=None
        )
        device = TOTPDevice.objects.get(user=user, confirmed=True)
        resp = client.post(
            "/" + settings.PORTAL_URL + "accounts/confirm/",
            {"password": PASSWORD, "code": format_token(totp_now(device))},
        )
        assert resp.status_code == 302, resp.content[:300]

    return _reauth
