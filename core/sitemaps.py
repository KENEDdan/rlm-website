from __future__ import annotations

from typing import Any

from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from branches.models import Branch
from events.models import Event
from news.models import Post
from programs.models import Activity, ActivityCategory
from resources.models import Resource

from .models import Page

STATIC_PAGES = [
    "core:home",
    "core:about",
    "leadership:list",
    "programs:list",
    "branches:list",
    "events:list",
    "media_library:gallery",
    "media_library:videos",
    "media_library:reports",
    "testimonies",
    "resources:list",
    "news:list",
    "registrations:volunteer",
    "membership:register",
    "discipleship:register",
    "finance:volunteer",
    "giving:partner",
    "giving:give",
    "prayer:request",
    "contact:contact",
]


class StaticSitemap(Sitemap):
    changefreq = "weekly"
    priority = 0.7

    def items(self) -> list[str]:
        return STATIC_PAGES

    def location(self, item: str) -> str:
        return reverse(item)


class PublishedSitemap(Sitemap):
    changefreq = "weekly"
    model: Any = None

    def items(self):  # type: ignore[no-untyped-def]
        return self.model.objects.published()

    def lastmod(self, obj: Any):  # type: ignore[no-untyped-def]
        return obj.updated_at


class BranchSitemap(PublishedSitemap):
    model = Branch


class ActivitySitemap(PublishedSitemap):
    model = Activity


class ActivityCategorySitemap(PublishedSitemap):
    model = ActivityCategory


class EventSitemap(PublishedSitemap):
    model = Event


class ResourceSitemap(PublishedSitemap):
    model = Resource


class PostSitemap(PublishedSitemap):
    model = Post
    priority = 0.6


class PageSitemap(PublishedSitemap):
    model = Page
    priority = 0.3


SITEMAPS = {
    "static": StaticSitemap,
    "branches": BranchSitemap,
    "activities": ActivitySitemap,
    "activity-categories": ActivityCategorySitemap,
    "events": EventSitemap,
    "resources": ResourceSitemap,
    "news": PostSitemap,
    "pages": PageSitemap,
}
