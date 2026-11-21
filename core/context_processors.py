from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import HttpRequest

from .models import SITE_SETTINGS_CACHE_KEY, Page, SiteContent, SiteSettings, SocialLink


def site(request: HttpRequest) -> dict[str, Any]:
    try:
        site_content = SiteContent.get()
        site_settings = SiteSettings.get()
        key = SITE_SETTINGS_CACHE_KEY + ":social"
        social = cache.get(key)
        if social is None:
            social = list(SocialLink.objects.filter(is_published=True))
            cache.set(key, social, 300)
        footer_pages = cache.get(SITE_SETTINGS_CACHE_KEY + ":footer-pages")
        if footer_pages is None:
            footer_pages = list(
                Page.objects.published()
                .filter(show_in_footer=True)
                .exclude(slug__in=["privacy", "terms"])
                .values("title", "slug")
            )
            cache.set(SITE_SETTINGS_CACHE_KEY + ":footer-pages", footer_pages, 300)
    except DatabaseError:  # e.g. during the very first migrate
        site_content, site_settings, social, footer_pages = (
            SiteContent(),
            SiteSettings(),
            [],
            [],
        )
    return {
        "site": site_content,  # what visitors see (Technical Team)
        "site_config": site_settings,  # analytics, retention (Super Admin)
        "social_links": social,
        "footer_pages": footer_pages,
        "turnstile_site_key": settings.TURNSTILE_SITE_KEY if settings.TURNSTILE_ENABLED else "",
        "site_url": settings.SITE_URL,
    }
