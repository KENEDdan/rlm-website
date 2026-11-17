"""Template helpers. Everything user-supplied is escaped; ``mark_safe`` is used only for constant SVG markup
defined in this file."""

from __future__ import annotations

import json
from typing import Any

from django import template
from django.templatetags.static import static
from django.utils.html import escape, format_html, format_html_join
from django.utils.safestring import SafeString, mark_safe

from core.uploads import RENDITION_WIDTHS, rendition_name

register = template.Library()

PLACEHOLDER_ALT = "Placeholder image: real photo coming soon"


@register.filter
def rendition(field: Any, width: int) -> str:
    """URL of an uploaded image's WebP rendition (``{{ site.logo|rendition:480 }}``); '' if no image."""
    if not field:
        return ""
    return field.storage.url(rendition_name(field.name, int(width)))


@register.simple_tag
def responsive_img(
    field: Any,
    alt: str = "",
    sizes: str = "(min-width: 1024px) 33vw, (min-width: 640px) 50vw, 100vw",
    css: str = "h-full w-full object-cover",
    eager: bool = False,
) -> SafeString:
    """<img> with a WebP srcset built from the renditions written by SafeImageField.
    Falls back to a clearly labelled placeholder when there is no image."""
    loading = "eager" if eager else "lazy"
    priority = "high" if eager else "auto"
    if not field:
        srcset = ", ".join(f"{static(f'brand/placeholder_w{w}.webp')} {w}w" for w in RENDITION_WIDTHS)
        return format_html(
            '<img src="{}" srcset="{}" sizes="{}" alt="{}" class="{}" loading="{}" decoding="async" '
            'fetchpriority="{}" width="1600" height="1000" data-placeholder="true">',
            static("brand/placeholder_w960.webp"),
            srcset,
            sizes,
            PLACEHOLDER_ALT,
            css,
            loading,
            priority,
        )
    storage, name = field.storage, field.name
    srcset = ", ".join(f"{storage.url(rendition_name(name, w))} {w}w" for w in RENDITION_WIDTHS)
    return format_html(
        '<img src="{}" srcset="{}" sizes="{}" alt="{}" class="{}" loading="{}" decoding="async" fetchpriority="{}">',
        storage.url(rendition_name(name, 960)),
        srcset,
        sizes,
        alt,
        css,
        loading,
        priority,
    )


@register.filter
def srcset(field: Any) -> str:
    """``srcset`` value of an uploaded image's WebP renditions (used for ``<link rel=preload>``)."""
    if not field:
        return ""
    return ", ".join(f"{field.storage.url(rendition_name(field.name, w))} {w}w" for w in RENDITION_WIDTHS)


@register.simple_tag(takes_context=True)
def render_slide(
    context: Any, template_name: str, item_name: str, item: Any, first: bool = False, index: int = 0
) -> SafeString:
    """Render one slide of ``includes/slider.html`` with the card template it was given.

    ``{% render_slide "includes/event_card.html" "event" item %}`` renders the card with ``event`` set to
    the item (like ``{% include ... with event=item %}``, but with the variable name chosen by the caller).
    ``slide_first`` (bool) and ``slide_index`` (0-based) are also available to the card template.
    The output is the rendered (auto-escaped) template, exactly as ``{% include %}`` would produce.
    """
    template = context.template.engine.get_template(template_name)
    with context.push(**{item_name: item, "slide_first": first, "slide_index": index}):
        return template.render(context)


@register.filter
def is_placeholder(field: Any) -> bool:
    return not field


@register.filter
def paragraphs(text: str | None) -> SafeString:
    """Plain text -> escaped <p>/<h2> blocks. Blank lines split paragraphs; '## ' starts a heading."""
    if not text:
        return SafeString("")
    blocks = [b.strip() for b in str(text).replace("\r\n", "\n").split("\n\n") if b.strip()]
    rendered = []
    for block in blocks:
        if block.startswith("## "):
            rendered.append(("h2", block[3:].strip(), ()))
        else:
            lines = block.split("\n")
            rendered.append(("p", lines[0], lines[1:]))
    out = []
    for tag, first, rest in rendered:
        if rest:
            body = format_html_join(format_html("<br>"), "{}", ((line,) for line in [first, *rest]))
            out.append(format_html("<{}>{}</{}>", tag, body, tag))
        else:
            out.append(format_html("<{}>{}</{}>", tag, first, tag))
    # Every fragment came from format_html/format_html_join, so all user text is already escaped.
    return SafeString("\n".join(out))  # nosec B703


@register.filter
def lines(text: str | None) -> list[str]:
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


@register.filter
def phone_href(number: str | None) -> str:
    digits = "".join(ch for ch in (number or "") if ch.isdigit() or ch == "+")
    return f"tel:{digits}" if digits else ""


# ---------------------------------------------------------------- icons (constant, trusted SVG)
ICONS: dict[str, str] = {
    "flame": '<path d="M12 2c1 3.5-1.5 5-1.5 8a3 3 0 0 0 6 0c0-1-.3-2-.8-2.8C18.5 9 20 11.5 20 14a8 8 0 1 1-16 0c0-4.5 4-6.5 5-9.5.4 1.6 1.5 2.5 3 2.5 0-2 .5-3.5 0-5Z"/>',
    "book": '<path d="M3 5.5C5.5 4 8.5 4 12 6c3.5-2 6.5-2 9-.5V19c-2.5-1.5-5.5-1.5-9 .5-3.5-2-6.5-2-9-.5V5.5Z"/><path d="M12 6v13.5"/>',
    "people": '<circle cx="9" cy="8" r="3.5"/><path d="M2.5 20c.6-3.6 3.3-6 6.5-6s5.9 2.4 6.5 6"/><circle cx="17" cy="9" r="2.5"/><path d="M16 14.2c2.8.2 4.9 2.3 5.5 5.3"/>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z"/>',
    "hands": '<path d="M12 21V11M12 11 8.5 4.5a1.5 1.5 0 0 0-2.7 1.2L8 13l-2 3 2.5 5M12 11l3.5-6.5a1.5 1.5 0 0 1 2.7 1.2L16 13l2 3-2.5 5"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 3Z"/>',
    "heart": '<path d="M12 20s-7.5-4.4-9-9.5C2 6.9 4.4 4.5 7.3 4.5c1.9 0 3.6 1 4.7 2.6 1.1-1.6 2.8-2.6 4.7-2.6 2.9 0 5.3 2.4 4.3 6C19.5 15.6 12 20 12 20Z"/>',
    "calendar": '<rect x="3" y="5" width="18" height="16" rx="2"/><path d="M3 10h18M8 3v4M16 3v4"/>',
    "pin": '<path d="M12 21s7-6.2 7-11.5A7 7 0 0 0 5 9.5C5 14.8 12 21 12 21Z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "arrow": '<path d="M5 12h14M13 6l6 6-6 6"/>',
    "menu": '<path d="M4 7h16M4 12h16M4 17h16"/>',
    "close": '<path d="M6 6l12 12M18 6 6 18"/>',
    "play": '<path d="M8 5v14l11-7L8 5Z" fill="currentColor"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7 9 6 9-6"/>',
    "phone": '<path d="M5 4h4l2 5-2.5 1.5a11 11 0 0 0 5 5L15 13l5 2v4a2 2 0 0 1-2 2A16 16 0 0 1 3 6a2 2 0 0 1 2-2Z"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "check": '<path d="m5 12 5 5L20 7"/>',
    "facebook": '<path d="M14 8h3V4h-3a4 4 0 0 0-4 4v3H7v4h3v7h4v-7h3l1-4h-4V8Z" fill="currentColor" stroke="none"/>',
    "instagram": '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.5" cy="6.5" r="1" fill="currentColor"/>',
    "tiktok": '<path d="M14 3v11.5a3.5 3.5 0 1 1-3.5-3.5M14 3c.5 2.8 2.3 4.5 5 4.8" />',
    "youtube": '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="m10 9 5 3-5 3V9Z" fill="currentColor"/>',
    "x": '<path d="M4 4l16 16M20 4 4 20"/>',
    "linkedin": '<rect x="3" y="3" width="18" height="18" rx="3"/><path d="M8 10v7M8 7v.01M12 17v-4a2 2 0 0 1 4 0v4M12 10v7"/>',
    "other": '<circle cx="12" cy="12" r="9"/><path d="M8 12h8"/>',
    "whatsapp": '<path d="M4 20l1.3-4A8 8 0 1 1 8 18.7L4 20Z"/><path d="M9 9.5c.3 2.4 2.1 4.2 4.5 4.5l1-1.2 2 .8c-.2 1.3-1.2 2-2.5 2A6 6 0 0 1 8 9.5c0-1.3.7-2.3 2-2.5l.8 2-1.3.5Z" fill="currentColor" stroke="none"/>',
}


@register.simple_tag
def icon(name: str, css: str = "h-6 w-6", label: str = "") -> SafeString:
    paths = ICONS.get(name, ICONS["other"])  # constant markup only
    aria = (
        format_html('role="img" aria-label="{}"', label) if label else format_html('aria-hidden="{}"', "true")
    )
    return format_html(
        '<svg class="{}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" '
        'stroke-linecap="round" stroke-linejoin="round" {}>{}</svg>',
        css,
        aria,
        mark_safe(paths),  # nosec B308 B703 - constant SVG from ICONS, never user input
    )


@register.inclusion_tag("includes/youtube.html")
def youtube(video_id: str, title: str = "Video") -> dict[str, Any]:
    """Lazy 'facade': a thumbnail + play button; the nocookie iframe loads only on click."""
    return {"video_id": video_id, "title": title}


@register.simple_tag(takes_context=True)
def organization_jsonld(context: dict[str, Any]) -> SafeString:
    site = context.get("site")
    request = context.get("request")
    if site is None or request is None:
        return SafeString("")
    base = context.get("site_url") or request.build_absolute_uri("/").rstrip("/")
    data: dict[str, Any] = {
        "@context": "https://schema.org",
        "@type": ["Organization", "NGO"],
        "name": site.ministry_name,
        "alternateName": site.short_name,
        "slogan": site.tagline,
        "url": base + "/",
        "logo": base
        + (rendition(site.logo, 960) if site.logo else static("brand/logo-transparent-640.webp")),
        "sameAs": [link.url for link in context.get("social_links", [])],
    }
    if site.public_email:
        data["email"] = site.public_email
    if site.public_phone:
        data["telephone"] = site.public_phone
    payload = json.dumps(data, ensure_ascii=False)
    # Same escaping as Django's json_script: neutralises </script> and HTML-significant characters.
    payload = payload.replace("<", "\\u003C").replace(">", "\\u003E").replace("&", "\\u0026")
    nonce = getattr(request, "csp_nonce", "")
    safe_payload = mark_safe(payload)  # nosec B308 B703 - JSON escaped like json_script
    return format_html('<script type="application/ld+json" nonce="{}">{}</script>', nonce, safe_payload)


@register.simple_tag
def absolute_static(request: Any, path: str) -> str:
    return escape(request.build_absolute_uri(static(path)))


@register.simple_tag
def page_text(key: str) -> Any:
    """``{% page_text "events" as pt %}`` -> editable eyebrow/heading/intro (admin: Page text)."""
    from core.site_text import page_text as lookup

    return lookup(key)


@register.inclusion_tag("core/_privacy_facts.html", takes_context=True)
def privacy_facts(context: dict[str, Any]) -> dict[str, Any]:
    """Cookie list and retention periods generated from the live settings, so the privacy page can never
    drift from what the site really does."""
    from django.conf import settings

    site = context.get("site")
    retention = [
        ("Prayer requests", getattr(site, "retention_prayer_days", 0)),
        ("Contact messages", getattr(site, "retention_contact_days", 0)),
        ("Volunteer applications", getattr(site, "retention_volunteer_days", 0)),
        ("Event registrations", getattr(site, "retention_event_registration_days", 0)),
        ("Partnership enquiries", getattr(site, "retention_partnership_days", 0)),
        ("Unconfirmed newsletter sign-ups", 30),
    ]
    cookies = [
        (
            settings.CSRF_COOKIE_NAME,
            "Security: protects forms against forgery",
            "Until you close the browser",
        ),
        ("messages", "Shows a one-off confirmation after you send a form", "Deleted when shown"),
        (
            settings.SESSION_COOKIE_NAME,
            "Staff sign-in only (not set for visitors)",
            "Until the browser closes; 2 h idle",
        ),
    ]
    return {"site": site, "retention": retention, "cookies": cookies}
