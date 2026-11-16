from __future__ import annotations

import logging

from django.db import connection
from django.http import HttpRequest, HttpResponse, HttpResponseServerError, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.template import loader
from django.urls import reverse
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_GET

from .models import Page

logger = logging.getLogger(__name__)


@require_GET
def healthz(request: HttpRequest) -> JsonResponse:
    try:
        with connection.cursor() as cur:
            cur.execute("SELECT 1")
    except Exception:
        logger.exception("Health check: database unavailable")
        return JsonResponse({"status": "error"}, status=503)
    return JsonResponse({"status": "ok"})


@require_GET
@cache_control(max_age=86400, public=True)
def robots_txt(request: HttpRequest) -> HttpResponse:
    sitemap = request.build_absolute_uri(reverse("sitemap"))
    lines = [
        "User-agent: *",
        "Disallow: /uploads/private/",
        "Disallow: /newsletter/",
        "Disallow: /payments/",
        f"Sitemap: {sitemap}",
    ]
    return HttpResponse("\n".join(lines) + "\n", content_type="text/plain")


def page_detail(request: HttpRequest, slug: str) -> HttpResponse:
    page = get_object_or_404(Page.objects.published(), slug=slug)
    return render(request, "core/page.html", {"page": page})


def ratelimited(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/429.html", status=429)


def csrf_failure(request: HttpRequest, reason: str = "") -> HttpResponse:
    return render(request, "errors/403_csrf.html", status=403)


def error_400(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/400.html", status=400)


def error_403(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/403.html", status=403)


def error_404(request: HttpRequest, exception: Exception | None = None) -> HttpResponse:
    return render(request, "errors/404.html", status=404)


def error_500(request: HttpRequest) -> HttpResponse:
    # Rendered WITHOUT the request context: no context processors, no DB access, nothing that can fail again.
    return HttpResponseServerError(loader.get_template("errors/500.html").render({}))
