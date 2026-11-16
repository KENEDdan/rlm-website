"""Cloudflare Turnstile server-side verification."""

from __future__ import annotations

import json
import logging
import urllib.parse
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def verify_turnstile(token: str, remote_ip: str | None = None) -> bool:
    """Return True when Turnstile is disabled or the token is valid. Fails closed on errors."""
    if not settings.TURNSTILE_ENABLED:
        return True
    if not token or len(token) > 2048:
        return False
    payload = {"secret": settings.TURNSTILE_SECRET_KEY, "response": token}
    if remote_ip:
        payload["remoteip"] = remote_ip
    data = urllib.parse.urlencode(payload).encode()
    req = urllib.request.Request(VERIFY_URL, data=data, method="POST")  # fixed https URL, no SSRF
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:  # noqa: S310  # nosec B310 - constant https URL
            result = json.loads(resp.read(65536))
    except (OSError, ValueError):
        logger.warning("Turnstile verification unavailable")
        return False
    return bool(result.get("success"))
