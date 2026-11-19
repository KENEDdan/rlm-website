"""Re-authentication ("sudo mode"): password AND a 2FA code again before sensitive account changes.

A successful re-authentication is valid for ``REAUTH_WINDOW_SECONDS`` (default 5 minutes) in this session
only. Creating users, changing roles, resetting 2FA, forcing a password reset and deleting all require it.
"""

from __future__ import annotations

import time

from django.conf import settings
from django.http import HttpRequest

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
