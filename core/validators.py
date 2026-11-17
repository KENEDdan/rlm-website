"""Validators shared by several apps."""

from __future__ import annotations

from urllib.parse import urlsplit

from django.core.exceptions import ValidationError

SAFE_LINK_HELP = (
    "A page on this website starting with / (for example /give/ or /events/), "
    "or a full secure link starting with https://"
)


def validate_safe_link(value: str) -> None:
    """Allow only a site-relative path ("/give/") or an absolute ``https://`` URL.

    Rejects ``javascript:``, ``data:``, ``http:``, protocol-relative ``//host`` links, backslash tricks
    (browsers treat ``/\\host`` like ``//host``), credentials in the URL, and any whitespace or control
    character (``java\\tscript:`` is executed by browsers that strip tabs).
    """
    text = value or ""
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise ValidationError("Links cannot contain spaces or hidden characters.", code="unsafe_link")
    if "\\" in text:
        raise ValidationError("Links cannot contain a backslash (\\).", code="unsafe_link")
    if text.startswith("/"):
        if text.startswith("//"):
            raise ValidationError(
                "Start with a single / for a page on this site, or use https://", code="unsafe_link"
            )
        return
    try:
        parts = urlsplit(text)
    except ValueError as exc:
        raise ValidationError("Enter a valid link.", code="unsafe_link") from exc
    if parts.scheme.lower() != "https" or not parts.hostname:
        raise ValidationError(
            "Use a page on this site starting with / or a secure link starting with https://",
            code="unsafe_link",
        )
    if parts.username or parts.password:
        raise ValidationError("Links cannot contain a user name or password.", code="unsafe_link")


def is_safe_link(value: str) -> bool:
    try:
        validate_safe_link(value)
    except ValidationError:
        return False
    return bool(value)
