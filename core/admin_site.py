from __future__ import annotations

from typing import Any

from django.contrib import admin
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils.http import urlencode


class RLMAdminSite(admin.AdminSite):
    """Admin that requires a 2FA-verified staff session. Login goes through accounts.views."""

    site_header = "Rebuilding Lives Ministry"
    site_title = "RLM admin"
    index_title = "Ministry administration"
    enable_nav_sidebar = True

    def has_permission(self, request: HttpRequest) -> bool:
        user = request.user
        return bool(user.is_active and user.is_staff and getattr(user, "is_verified", lambda: False)())

    def login(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        url = reverse("accounts:login")
        nxt = request.GET.get("next")
        return redirect(f"{url}?{urlencode({'next': nxt})}" if nxt else url)

    def logout(self, request: HttpRequest, extra_context: dict[str, Any] | None = None) -> HttpResponse:
        from accounts.views import logout_view

        return logout_view(request)
