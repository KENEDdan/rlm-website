"""Deployment system checks for security settings Django does not check itself."""

from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import Error, Tags, Warning, register


@register(Tags.security, deploy=True)
def turnstile_check(app_configs: Any, **kwargs: Any) -> list[Warning | Error]:
    if not settings.TURNSTILE_ENABLED:
        return [
            Warning(
                "Cloudflare Turnstile is disabled; public forms rely on honeypot and rate limits only.",
                hint="Set TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY (CLAUDE.md rule 7).",
                id="rlm.W001",
            )
        ]
    if not (settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY):
        return [
            Error(
                "Turnstile is enabled but its keys are missing: every public form submission will be rejected.",
                hint="Set TURNSTILE_SITE_KEY and TURNSTILE_SECRET_KEY.",
                id="rlm.E001",
            )
        ]
    return []
