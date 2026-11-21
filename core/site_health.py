"""Website health for the Technical Team dashboard: links, images, storage, backups, uptime, pages to review.

Only website content is inspected (never personal or financial records). Links are checked WITHOUT calling
other websites: internal links ("/give/") must resolve to a page of this site, external ones must be valid
``https://`` links. Images and videos must exist in storage.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.core.cache import cache
from django.db import connection
from django.urls import Resolver404, resolve
from django.utils import timezone

from .validators import is_safe_link

STARTED_AT = time.time()
STORAGE_CACHE_KEY = "core:site-health:storage:v1"
PAGE_REVIEW_DAYS = 365
BACKUP_STALE_HOURS = 36


@dataclass
class Problem:
    where: str
    field: str
    value: str
    problem: str
    admin_url: str = ""


def _admin_url(obj: Any) -> str:
    from django.urls import NoReverseMatch, reverse

    opts = obj._meta
    try:
        return reverse(f"admin:{opts.app_label}_{opts.model_name}_change", args=[obj.pk])
    except NoReverseMatch:
        return ""


def check_link(value: str) -> str:
    """'' if fine, else what is wrong."""
    if not value:
        return ""
    if not is_safe_link(value):
        return "Not a safe link (use /page/ on this site or https://)."
    if value.startswith("/"):
        path = value.split("?", 1)[0].split("#", 1)[0]
        try:
            resolve(path)
        except Resolver404:
            return "No page on this website has this address."
    return ""


def link_targets() -> list[tuple[Any, str]]:
    from programs.models import Activity

    from .models import HeroSettings, HeroSlide, Partner

    out: list[tuple[Any, str]] = []
    for model, fields in (
        (HeroSlide, ("button_link", "button2_link")),
        (HeroSettings, ("button_link", "button2_link")),
        (Partner, ("website",)),
        (Activity, ("cta_link",)),
    ):
        for obj in model.objects.all():
            out += [(obj, f) for f in fields]
    return out


def file_targets() -> list[tuple[Any, str]]:
    from branches.models import Branch
    from leadership.models import Leader
    from media_library.models import Album
    from news.models import Post
    from programs.models import Activity, ActivityCategory

    from .models import HeroSettings, HeroSlide, Partner, SiteContent

    out: list[tuple[Any, str]] = []
    for model, fields in (
        (SiteContent, ("logo", "logo_on_dark", "favicon")),
        (HeroSettings, ("image", "video", "video_poster")),
        (HeroSlide, ("image", "video", "video_poster")),
        (Partner, ("logo",)),
        (ActivityCategory, ("image",)),
        (Activity, ("image",)),
        (Leader, ("photo",)),
        (Branch, ("image",)),
        (Album, ("cover",)),
        (Post, ("image",)),
    ):
        for obj in model.objects.all():
            out += [(obj, f) for f in fields if getattr(obj, f)]
    return out


def broken_links_and_files() -> list[Problem]:
    problems: list[Problem] = []
    for obj, field in link_targets():
        value = getattr(obj, field) or ""
        issue = check_link(value)
        if issue:
            problems.append(
                Problem(str(obj), obj._meta.get_field(field).verbose_name, value, issue, _admin_url(obj))
            )
    for obj, field in file_targets():
        file = getattr(obj, field)
        try:
            exists = file.storage.exists(file.name)
        except Exception:  # noqa: BLE001 - an unreadable storage counts as missing
            exists = False
        if not exists:
            problems.append(
                Problem(
                    str(obj),
                    obj._meta.get_field(field).verbose_name,
                    "",
                    "The file is missing.",
                    _admin_url(obj),
                )
            )
    return problems


def _dir_size(root: str) -> tuple[int, int]:
    total = count = 0
    for base, _dirs, files in os.walk(root):
        for name in files:
            try:
                total += os.path.getsize(os.path.join(base, name))
                count += 1
            except OSError:
                continue
    return total, count


def storage_usage(refresh: bool = False) -> dict[str, Any]:
    """Size of the public uploads and (total only, never names) the private files. Cached for 10 minutes."""
    data = None if refresh else cache.get(STORAGE_CACHE_KEY)
    if data is None:
        public_bytes, public_files = _dir_size(str(settings.MEDIA_ROOT))
        private_bytes, private_files = _dir_size(str(settings.PRIVATE_MEDIA_ROOT))
        data = {
            "public_mb": round(public_bytes / 1024 / 1024, 1),
            "public_files": public_files,
            "private_mb": round(private_bytes / 1024 / 1024, 1),
            "private_files": private_files,
            "measured_at": timezone.now(),
        }
        cache.set(STORAGE_CACHE_KEY, data, 600)
    return data


def backup_status() -> dict[str, Any]:
    from .models import BackupRun

    last = BackupRun.objects.first()
    last_ok = BackupRun.objects.filter(ok=True).first()
    stale = last_ok is None or last_ok.finished_at < timezone.now() - timedelta(hours=BACKUP_STALE_HOURS)
    return {"last": last, "last_ok": last_ok, "stale": stale}


def uptime() -> dict[str, Any]:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
        database = True
    except Exception:  # noqa: BLE001
        database = False
    seconds = int(time.time() - STARTED_AT)
    return {"database": database, "since": timezone.now() - timedelta(seconds=seconds), "seconds": seconds}


def pages_needing_update() -> list[dict[str, Any]]:
    """Published pages never reviewed or not reviewed within a year, drafts, and activities without a photo."""
    from programs.models import Activity

    from .models import Page

    today = timezone.localdate()
    out = []
    for page in Page.objects.all():
        if not page.is_published:
            reason = "Not published yet"
        elif page.last_reviewed is None:
            reason = "Never reviewed"
        elif page.last_reviewed < today - timedelta(days=PAGE_REVIEW_DAYS):
            reason = f"Last reviewed {page.last_reviewed:%d %b %Y}"
        elif "draft" in page.body.lower()[:200]:
            reason = "Still marked as a draft"
        else:
            continue
        out.append({"title": page.title, "reason": reason, "url": _admin_url(page)})
    for activity in Activity.objects.published().filter(image=""):
        out.append({"title": activity.title, "reason": "Activity has no photo", "url": _admin_url(activity)})
    return out
