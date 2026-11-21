from __future__ import annotations

import contextlib
import ipaddress
from collections.abc import Callable

from django.conf import settings
from django.http import HttpRequest, HttpResponse


class RealIPMiddleware:
    """Use the client IP set by our own reverse proxy (Caddy ``X-Real-IP``) when trusted.

    Never trusts client-supplied headers unless ``TRUST_PROXY_IP_HEADER`` is on, which is only the case
    behind Caddy, which overwrites the header.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if settings.TRUST_PROXY_IP_HEADER:
            real_ip = request.META.get("HTTP_X_REAL_IP", "").strip()
            with contextlib.suppress(ValueError):
                request.META["REMOTE_ADDR"] = str(ipaddress.ip_address(real_ip))
        return self.get_response(request)


class RequestSizeLimitMiddleware:
    """Refuse oversized request bodies (413) before Django parses them.

    Public pages accept no file uploads, so their cap is small; the Django admin and staff portal allow the
    largest upload policy. Caddy's ``request_body max_size`` enforces the staff cap first in production and
    also covers chunked bodies without a Content-Length.
    """

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.staff_prefixes = ("/" + settings.ADMIN_URL, "/" + settings.PORTAL_URL)

    def __call__(self, request: HttpRequest) -> HttpResponse:
        try:
            length = int(request.META.get("CONTENT_LENGTH") or 0)
        except ValueError:
            return HttpResponse("Bad request.", status=400, content_type="text/plain")
        staff = request.path.startswith(self.staff_prefixes)
        limit = settings.MAX_STAFF_REQUEST_BYTES if staff else settings.MAX_PUBLIC_REQUEST_BYTES
        if length > limit:
            return HttpResponse(
                f"The request is too large (maximum {limit // (1024 * 1024)} MB).",
                status=413,
                content_type="text/plain",
            )
        return self.get_response(request)


class SecurityHeadersMiddleware:
    """Headers Django does not set itself, plus no-store caching for staff pages."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response
        self.admin_prefix = "/" + settings.ADMIN_URL

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.headers.setdefault("Permissions-Policy", settings.PERMISSIONS_POLICY)
        response.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        if request.path.startswith(self.admin_prefix):
            response.headers["Cache-Control"] = "no-store, private"
            response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response
