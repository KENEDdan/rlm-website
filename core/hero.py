"""Hero helpers: readability (WCAG contrast) check and the draft -> preview -> publish -> revert flow.

Contrast check: when a photo or poster is uploaded we measure the luminance of its BRIGHTEST areas (90th
percentile of a small copy), since text over a bright patch is what becomes unreadable. The dark overlay
(rlm-black at 0-80 %) is blended on top, and the result is compared with the chosen text colour. Below 4.5:1
(WCAG AA for normal text) the portal and admin show a warning; nothing is blocked, the editor decides.
"""

from __future__ import annotations

from typing import Any

from django.db import transaction
from django.http import HttpRequest
from django.utils import timezone
from PIL import Image

from audit.models import AuditLog
from audit.services import log_event

AA_NORMAL = 4.5
BLACK_LUMINANCE = 0.0030  # #0A0A0A, the brand black used for the overlay and dark text
WHITE_LUMINANCE = 1.0


def _channel(value: float) -> float:
    c = value / 255
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def measure_luminance(file: Any) -> float | None:
    """Relative luminance (0-1) of the brightest 10 % of the image; None if it cannot be read."""
    try:
        file.seek(0)
        with Image.open(file) as img:
            small = img.convert("RGB")
            small.thumbnail((64, 64))
            values = sorted(
                0.2126 * _channel(r) + 0.7152 * _channel(g) + 0.0722 * _channel(b)
                for r, g, b in small.getdata()
            )
        file.seek(0)
    except Exception:  # noqa: BLE001 - a missing or unreadable file just means "unknown"
        return None
    if not values:
        return None
    return round(values[int(len(values) * 0.9) - 1 if len(values) > 1 else 0], 4)


def ratio(l1: float, l2: float) -> float:
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


def contrast_ratio(background: str, luminance: float | None, overlay_percent: int, tone: str) -> float:
    """Contrast between the text colour and what is behind it."""
    text = WHITE_LUMINANCE if tone == "light" else BLACK_LUMINANCE
    if background == "theme" or luminance is None:
        behind = BLACK_LUMINANCE  # brand black (the flame accent is decoration, not behind the text)
    else:
        alpha = max(0, min(80, overlay_percent)) / 100
        behind = luminance * (1 - alpha) + BLACK_LUMINANCE * alpha
    return round(ratio(text, behind), 2)


def contrast_message(hero: Any) -> str:
    if hero.contrast_ok:
        return ""
    tip = (
        "Increase the dark overlay or choose dark text."
        if hero.text_tone == "light"
        else "Choose light text, or lower the overlay on a bright photo."
    )
    return (
        f"Readability warning: text contrast is about {hero.contrast_ratio}:1, below the 4.5:1 that WCAG AA "
        f"requires. {tip}"
    )


# ---------------------------------------------------------------------------------------------- publish
@transaction.atomic
def publish(request: HttpRequest) -> Any:
    """Copy the draft hero to the live one (versioned, so the previous live hero can be restored)."""
    from .models import ContentVersion, HeroSettings
    from .versioning import history, record

    draft, live = HeroSettings.draft(), HeroSettings.live()
    if not history(live).exists():  # keep the very first live hero so it can be restored
        record(live, ContentVersion.Action.CHANGE, request=request, note="Live hero before publishing")
    live.copy_from(draft)
    live.published_at, live.published_by = timezone.now(), request.user
    live.save()
    record(live, ContentVersion.Action.PUBLISH, request=request, note="Draft published")
    log_event(AuditLog.Action.CHANGE, request=request, obj=live, extra={"step": "publish"})
    return live


def previous_live_version(live: Any) -> Any:
    """The live hero's version before the current one (what "Revert to previous" restores)."""
    from .versioning import history

    versions = list(history(live)[:2])
    return versions[1] if len(versions) > 1 else None


@transaction.atomic
def revert(request: HttpRequest) -> Any:
    from .models import HeroSettings
    from .versioning import restore

    live = HeroSettings.live()
    version = previous_live_version(live)
    if version is None:
        raise LookupError("There is no earlier live hero to go back to.")
    return restore(version, request)
