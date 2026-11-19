"""Media & Communications: content pipeline, design requests from other departments, testimonies, archive."""

from __future__ import annotations

from datetime import timedelta

import pytest
from django.conf import settings
from django.test import Client
from django.utils import timezone

from accounts.roles import FINANCE, MEDIA, MISSIONS
from communications.models import ContentItem, DesignRequest, SocialReach
from events.models import Event
from media_library.models import Testimony
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


def _testimony(**kw) -> Testimony:  # type: ignore[no-untyped-def]
    data = {
        "title": "Healed",
        "slug": f"t{Testimony.objects.count()}",
        "body": "Praise God",
        "consent_confirmed": True,
        "is_published": True,
    }
    data.update(kw)
    return Testimony.objects.create(**data)


def test_other_departments_request_designs_and_see_only_their_own(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    missions = verified_client(make_staff(MISSIONS))
    resp = missions.post(
        P + "media/design-requests/new/",
        {
            "title": "Crusade poster",
            "kind": "poster",
            "requesting_department": dept("missions").pk,
            "needed_by": (timezone.localdate() + timedelta(days=10)).isoformat(),
            "brief": "A3, Juba crusade",
            "status": "delivered",  # not on the requester's form: ignored
        },
    )
    assert resp.status_code == 302
    req = DesignRequest.objects.get()
    assert req.status == "new" and req.requested_by is not None
    DesignRequest.objects.create(
        title="Finance report cover",
        kind="other",
        requesting_department=dept("finance"),
        needed_by=timezone.localdate(),
        brief="x",
    )
    listing = missions.get(P + "media/design-requests/").content.decode()
    assert "Crusade poster" in listing and "Finance report cover" not in listing
    assert missions.get(P + "media/").status_code == 403
    assert missions.get(P + "media/content/").status_code == 403
    assert missions.get(P + f"media/design-requests/{req.pk}/edit/").status_code == 403


def test_testimony_approval_requires_consent_and_adult(make_staff, verified_client, client: Client) -> None:  # type: ignore[no-untyped-def]
    head = verified_client(make_staff(MEDIA, heads={"media"}))
    child = _testimony(title="Child story", person_display_name="Young One")
    head.post(P + f"media/testimonies/{child.pk}/approval/", {"approve": "1"})
    child.refresh_from_db()
    assert not child.is_approved
    adult = _testimony(title="Adult story", subject_is_adult=True)
    member = verified_client(make_staff(MEDIA))
    assert member.post(P + f"media/testimonies/{adult.pk}/approval/", {"approve": "1"}).status_code == 403
    head.post(P + f"media/testimonies/{adult.pk}/approval/", {"approve": "1"})
    adult.refresh_from_db()
    assert adult.is_approved
    page = client.get("/testimonies/").content.decode()
    assert "Adult story" in page and "Child story" not in page


def test_unconfirmed_adult_testimony_never_public(client: Client) -> None:
    Testimony.objects.create(
        title="Hidden", slug="hidden", body="x", consent_confirmed=True, is_published=True, is_approved=True
    )
    assert "Hidden" not in client.get("/testimonies/").content.decode()


def test_media_manages_hero_slides_and_albums_in_portal(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    client = verified_client(make_staff(MEDIA))
    assert client.get(P + "media/hero-slides/").status_code == 200
    assert client.get(P + "media/albums/").status_code == 200
    assert verified_client(make_staff(FINANCE)).get(P + "media/hero-slides/").status_code == 403


def test_media_dashboard(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    today = timezone.localdate()
    ContentItem.objects.create(
        title="Sunday recap", channel="facebook", stage="published", planned_date=today
    )
    ContentItem.objects.create(title="Youth reel", channel="tiktok", stage="production", planned_date=today)
    start = timezone.now() + timedelta(days=5)
    Event.objects.create(
        title="Youth conference",
        slug="yc",
        summary="x",
        start=start,
        end=start + timedelta(hours=3),
        is_published=True,
    )
    SocialReach.objects.create(month=today, channel="facebook", reach=1200)
    page = verified_client(make_staff(MEDIA)).get(P + "media/")
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert (
        kpis["published_vs_planned"] == "1 / 2"
        and kpis["events_uncovered"] == 1
        and kpis["social_reach"] == "1,200"
    )
    assert any("Youth conference" in i.text for i in page.context["board"].attention)
