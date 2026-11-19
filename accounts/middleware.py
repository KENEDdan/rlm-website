from __future__ import annotations

from collections.abc import Callable

from django.conf import settings
from django.contrib.auth import logout
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect


class StaffTwoFactorMiddleware:
    """Defence in depth: any authenticated session that has not passed 2FA is logged out
    as soon as it touches the admin area or the staff portal. The normal flow never creates such sessions,
    but this catches sessions created by any other path (shell, tests, future code)."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.admin_prefix = "/" + settings.ADMIN_URL
        self.account_prefix = self.admin_prefix + "account/"
        self.portal_prefix = "/" + settings.PORTAL_URL

    def __call__(self, request: HttpRequest) -> HttpResponse:
        user = getattr(request, "user", None)
        if (
            user is not None
            and user.is_authenticated
            and (
                (
                    request.path.startswith(self.admin_prefix)
                    and not request.path.startswith(self.account_prefix)
                )
                or request.path.startswith(self.portal_prefix)
            )
            and not user.is_verified()
        ):
            logout(request)
            return redirect("accounts:login")
        return self.get_response(request)
