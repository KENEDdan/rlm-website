"""Smoke test: with the demo data loaded, every portal screen renders for the Super Admin."""

from __future__ import annotations

from io import StringIO

import pytest
from django.conf import settings
from django.core.management import call_command
from django.test import override_settings

from membership.models import Member
from portal.access import DEPARTMENT_ORDER
from portal.resources import REGISTRY

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


@pytest.fixture
def demo() -> None:
    with override_settings(DEBUG=True):
        call_command("seed_demo", "--no-images", stdout=StringIO())


def test_every_dashboard_and_screen_renders(demo, make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(superuser=True))
    assert client.get(P + "executive/").status_code == 200
    for code in DEPARTMENT_ORDER:
        assert client.get(P + f"{code}/").status_code == 200, code
        assert client.get(P + f"{code}/export/print/").status_code == 200, code
        assert client.get(P + f"{code}/my-budget/").status_code == 200, code
    for (department, slug), resource in REGISTRY.items():
        base = P + f"{department}/{slug}/"
        assert client.get(base).status_code == 200, base
        obj = resource.get_queryset(resource_access(client)).first()
        if obj is None:
            continue
        assert client.get(f"{base}{obj.pk}/").status_code == 200, (base, obj.pk)
        if resource.fields is not None and resource.can(resource_access(client), "change", obj):
            assert client.get(f"{base}{obj.pk}/edit/").status_code == 200, (base, obj.pk)


def resource_access(client):  # type: ignore[no-untyped-def]
    from accounts.models import User
    from portal.access import Access

    return Access(User.objects.get(pk=client.session["_auth_user_id"]))


def test_demo_reset_removes_portal_demo_rows(demo) -> None:  # type: ignore[no-untyped-def]
    assert Member.objects.exists()
    with override_settings(DEBUG=True):
        call_command("seed_demo", "--reset", stdout=StringIO())
    assert not Member.objects.exists()
