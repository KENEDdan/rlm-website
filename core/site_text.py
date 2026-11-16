"""Read editable page text and form options (cached), with safe fallbacks to the built-in defaults."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.core.cache import cache
from django.db import DatabaseError

from .page_texts import FORM_OPTION_DEFAULTS, PAGE_TEXT_DEFAULTS

CACHE_SECONDS = 300


@dataclass(frozen=True)
class Text:
    key: str
    eyebrow: str = ""
    heading: str = ""
    highlight: str = ""
    intro: str = ""
    seo_title: str = ""
    seo_description: str = ""


def _cache_key(suffix: str) -> str:
    from .models import SITE_TEXT_CACHE_KEY

    return f"{SITE_TEXT_CACHE_KEY}:{suffix}"


def _all_page_texts() -> dict[str, Text]:
    data = cache.get(_cache_key("pages"))
    if data is None:
        from .models import PageText

        fields = ("key", "eyebrow", "heading", "highlight", "intro", "seo_title", "seo_description")
        try:
            data = {row["key"]: Text(**row) for row in PageText.objects.values(*fields)}
        except DatabaseError:  # e.g. before the first migrate: fall back to defaults, don't cache
            return {}
        cache.set(_cache_key("pages"), data, CACHE_SECONDS)
    return data


def page_text(key: str) -> Text:
    """Edited text for ``key``; built-in default if no row exists; empty text for an unknown key."""
    found = _all_page_texts().get(key)
    if found is not None:
        return found
    default = PAGE_TEXT_DEFAULTS.get(key, {})
    return Text(
        key=key,
        eyebrow=default.get("eyebrow", ""),
        heading=default.get("heading", ""),
        highlight=default.get("highlight", ""),
        intro=default.get("intro", ""),
    )


def _options(list_name: str) -> list[tuple[str, str, bool]]:
    """[(value, label, is_active)] in display order."""
    key = _cache_key(f"options:{list_name}")
    data = cache.get(key)
    if data is None:
        from .models import FormOption

        try:
            data = list(FormOption.objects.filter(list=list_name).values_list("value", "label", "is_active"))
        except DatabaseError:
            data = []
        if not data:  # nothing configured yet: use the built-in list rather than an empty form
            data = [(v, label, True) for v, label in FORM_OPTION_DEFAULTS.get(list_name, [])]
        cache.set(key, data, CACHE_SECONDS)
    return data


def option_choices(list_name: str, *, include_inactive: bool = False) -> list[tuple[str, str]]:
    return [(v, label) for v, label, active in _options(list_name) if active or include_inactive]


def option_label(list_name: str, value: str | None) -> str:
    """Readable label for a stored value (also for switched-off options); the raw value if unknown."""
    if not value:
        return ""
    return next((label for v, label, _ in _options(list_name) if v == value), value)


def ensure_defaults(**kwargs: Any) -> None:
    """post_migrate: create missing page-text rows and seed empty option lists. Never overwrites edits."""
    from .models import FormOption, PageText

    for key, default in PAGE_TEXT_DEFAULTS.items():
        PageText.objects.get_or_create(
            key=key,
            defaults={
                "label": default["label"],
                "eyebrow": default.get("eyebrow", ""),
                "heading": default.get("heading", ""),
                "highlight": default.get("highlight", ""),
                "intro": default.get("intro", ""),
            },
        )
    for list_name, options in FORM_OPTION_DEFAULTS.items():
        if not FormOption.objects.filter(list=list_name).exists():
            FormOption.objects.bulk_create(
                [
                    FormOption(list=list_name, value=value, label=label, order=i * 10)
                    for i, (value, label) in enumerate(options)
                ]
            )
    cache.delete_many(
        [_cache_key("pages"), *(_cache_key(f"options:{name}") for name in FORM_OPTION_DEFAULTS)]
    )
