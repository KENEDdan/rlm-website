"""Rate-limit decorators shared by public forms and staff login (rates come from settings)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.conf import settings
from django.http import HttpRequest
from django_ratelimit.decorators import ratelimit


def _form_rate(group: str, request: HttpRequest) -> str:
    return settings.FORM_RATE


def _login_rate(group: str, request: HttpRequest) -> str:
    return settings.LOGIN_RATE


def form_ratelimit(view: Callable[..., Any]) -> Callable[..., Any]:
    """Limit POSTs per client IP. Exceeding the limit renders the 429 page."""
    return ratelimit(key="ip", rate=_form_rate, method="POST", block=True)(view)


def login_ratelimit(view: Callable[..., Any]) -> Callable[..., Any]:
    return ratelimit(key="ip", rate=_login_rate, method="POST", block=True)(view)
