"""Testimony approval (Media head): consent and the adult confirmation are re-checked by the model."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from audit.services import log_event
from portal.access import HEAD, portal_view
from portal.views import post_action

DEPT = "media"


@never_cache
@portal_view(DEPT, level=HEAD)
@require_POST
def testimony_approval(request: HttpRequest, pk: int) -> HttpResponse:
    resource, testimony = post_action(request, DEPT, "testimonies", pk, "change")
    approve = request.POST.get("approve") == "1"
    testimony.is_approved = approve
    try:
        testimony.full_clean()
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
        return redirect(resource.url("detail", testimony))
    testimony.save()
    log_event(AuditLog.Action.APPROVE if approve else AuditLog.Action.REJECT, request=request, obj=testimony)
    messages.success(request, "Approved for the website." if approve else "Approval withdrawn.")
    return redirect(resource.url("detail", testimony))
