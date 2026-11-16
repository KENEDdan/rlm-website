from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import DatabaseError
from django.http import HttpRequest

from .models import SITE_SETTINGS_CACHE_KEY, SiteSettings, SocialLink


def site(request: HttpRequest) -> dict[str, Any]:
    try:
        site_settings = SiteSettings.get()
        key = SITE_SETTINGS_CACHE_KEY + ":social"
        social = cache.get(key)
        if social is None:
            social = list(SocialLink.objects.filter(is_published=True))
            cache.set(key, social, 300)
    except DatabaseError:  # e.g. during the very first migrate
        site_settings, social = SiteSettings(), []
    return {
        "site": site_settings,
        "social_links": social,
        "turnstile_site_key": settings.TURNSTILE_SITE_KEY if settings.TURNSTILE_ENABLED else "",
        "site_url": settings.SITE_URL,
    }
