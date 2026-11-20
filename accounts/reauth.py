"""Re-authentication ("sudo mode"): password AND a 2FA code again before sensitive account changes.

A successful re-authentication is valid for ``REAUTH_WINDOW_SECONDS`` (default 5 minutes) in this session
only. Creating users, changing roles, resetting 2FA, forcing a password reset and deleting all require it.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from functools import wraps
from typing import Any

from django.conf import settings
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme, urlencode

SESSION_KEY = "reauth_at"


class ReauthRequired(Exception):
    pass


def is_fresh(request: HttpRequest) -> bool:
    stamp = request.session.get(SESSION_KEY)
    if not isinstance(stamp, int | float):
        return False
    return 0 <= time.time() - stamp <= settings.REAUTH_WINDOW_SECONDS


def mark_fresh(request: HttpRequest) -> None:
    request.session[SESSION_KEY] = int(time.time())


def clear(request: HttpRequest) -> None:
    request.session.pop(SESSION_KEY, None)


def require_reauth(
    fallback: str = "portal:home",
) -> Callable[[Callable[..., HttpResponse]], Callable[..., HttpResponse]]:
    """View decorator: password + 2FA again (within the window) before the screen or its POST runs.

    GET requests come back to the same page afterwards; POSTs come back to the page they were sent from.
    """

    def decorator(view: Callable[..., HttpResponse]) -> Callable[..., HttpResponse]:
        @wraps(view)
        def wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> HttpResponse:
            if not is_fresh(request):
                target = (
                    request.get_full_path()
                    if request.method == "GET"
                    else request.META.get("HTTP_REFERER", "")
                )
                if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}):
                    target = reverse(fallback)
                return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': target})}")
            try:
                return view(request, *args, **kwargs)
            except ReauthRequired:
                return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': reverse(fallback)})}")

        return wrapper

    return decorator
