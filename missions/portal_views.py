"""Missions: submit a campaign / mission-trip budget for executive approval (decision 3)."""

from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from finance.approvals import submit_budget
from portal.access import MEMBER, portal_view
from portal.views import post_action

DEPT = "missions"


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def budget_submit(request: HttpRequest, pk: int) -> HttpResponse:
    resource, campaign = post_action(request, DEPT, "campaigns", pk, "change")
    try:
        submit_budget(request, campaign, campaign.budget_request)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Budget submitted for executive approval.")
    return redirect(resource.url("detail", campaign))
