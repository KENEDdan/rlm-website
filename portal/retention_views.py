"""Super Admin: application retention (ministry decision 8): dry-run preview, legal holds, early deletion."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from django.contrib import messages
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts import reauth
from core import retention
from core.models import ApplicationStat, SiteSettings

from .access import get_access, portal_view


def _stats() -> list[dict[str, Any]]:
    since = timezone.localdate().replace(day=1).replace(year=timezone.localdate().year - 1)
    table: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for row in ApplicationStat.objects.filter(month__gte=since):
        table[row.kind][row.outcome] += row.count
    return [
        {
            "label": spec.label,
            "successful": table[code]["successful"],
            "unsuccessful": table[code]["unsuccessful"],
            "pending": table[code]["pending"],
        }
        for code, spec in retention.SPECS.items()
    ]


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def retention_screen(request: HttpRequest) -> HttpResponse:
    access = get_access(request)
    if not access.is_super_admin:
        raise PermissionDenied
    if request.method == "POST":
        action = request.POST.get("action", "")
        # deleting, or lifting a hold (which lets the nightly job delete), needs the password and code again
        if action in ("purge", "erase", "release") and not reauth.is_fresh(request):
            return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': reverse('portal:retention')})}")
        try:
            if action == "purge":
                result = retention.purge(dry_run=False, request=request)
                messages.success(
                    request,
                    f"Retention run finished: {result['deleted']} deleted, {result['skipped']} skipped.",
                )
            elif action in ("hold", "release"):
                retention.set_legal_hold(
                    request,
                    request.POST.get("kind", ""),
                    int(pk) if (pk := request.POST.get("pk", "")).isdigit() else 0,
                    on=action == "hold",
                    reason=request.POST.get("reason", ""),
                )
                messages.success(request, "Legal hold set." if action == "hold" else "Legal hold lifted.")
            elif action == "erase":
                pk_raw = request.POST.get("pk", "")
                retention.erase_on_request(
                    request,
                    request.POST.get("kind", ""),
                    int(pk_raw) if pk_raw.isdigit() else 0,
                    reason=request.POST.get("reason", ""),
                )
                messages.success(request, "Deleted. Only an anonymous count was kept.")
            else:
                raise PermissionDenied
        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("portal:retention")
    site = SiteSettings.load()
    preview = retention.purge(dry_run=True)
    return render(
        request,
        "portal/retention.html",
        {
            "site": site,
            "due": preview["candidates"],
            "due_counts": preview["due"],
            "nearing": retention.nearing(),
            "held": retention.held(),
            "stats": _stats(),
            "kinds": [(s.code, s.label) for s in retention.SPECS.values()],
            "fresh": reauth.is_fresh(request),
        },
    )
