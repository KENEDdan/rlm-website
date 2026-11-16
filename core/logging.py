"""PII scrubbing for logs and Sentry events (CLAUDE.md rule 14)."""

from __future__ import annotations

import logging
import re
from typing import Any

EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w.])\+?\d[\d ()-]{7,}\d")
FERNET_RE = re.compile(r"gAAAAA[A-Za-z0-9_\-=]{20,}")

SENSITIVE_KEYS = {
    "password",
    "passwd",
    "secret",
    "token",
    "otp",
    "email",
    "phone",
    "name",
    "full_name",
    "request_text",
    "message",
    "testimony",
    "church_affiliation",
    "csrfmiddlewaretoken",
    "cookie",
    "authorization",
    "sessionid",
}


def scrub_text(text: str) -> str:
    text = EMAIL_RE.sub("[email]", text)
    text = PHONE_RE.sub("[phone]", text)
    return FERNET_RE.sub("[ciphertext]", text)


def scrub_data(data: Any) -> Any:
    if isinstance(data, dict):
        return {
            k: ("[scrubbed]" if any(s in str(k).lower() for s in SENSITIVE_KEYS) else scrub_data(v))
            for k, v in data.items()
        }
    if isinstance(data, list | tuple):
        return type(data)(scrub_data(v) for v in data)
    if isinstance(data, str):
        return scrub_text(data)
    return data


class PIIScrubFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 - never let logging crash the app
            return True
        record.msg = scrub_text(message)
        record.args = None
        return True


def sentry_before_send(event: dict[str, Any], hint: dict[str, Any]) -> dict[str, Any]:
    request = event.get("request")
    if isinstance(request, dict):
        request.pop("data", None)
        request.pop("cookies", None)
        request.pop("query_string", None)
        headers = request.get("headers") or {}
        request["headers"] = {
            k: v for k, v in headers.items() if k.lower() in {"user-agent", "referer", "host"}
        }
    event.pop("user", None)
    return scrub_data(event)
