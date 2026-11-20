"""Development -> Finance: a capital proposal becomes a funding proposal in Finance's tracker."""

from __future__ import annotations

from django.contrib import messages
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from audit.models import AuditLog
from audit.services import log_event
from finance.models import Proposal
from portal.access import HEAD, MEMBER, portal_view
from portal.views import post_action

from .models import CapitalProposal

DEPT = "development"


@never_cache
@portal_view(DEPT, level=HEAD)
@require_POST
def send_to_finance(request: HttpRequest, pk: int) -> HttpResponse:
    resource, proposal = post_action(request, DEPT, "capital-proposals", pk, "view")
    if proposal.status != CapitalProposal.Status.DRAFT:
        messages.error(request, "This proposal was already sent.")
        return redirect(resource.url("detail", proposal))
    with transaction.atomic():
        finance_proposal = Proposal.objects.create(
            kind=Proposal.Kind.PROPOSAL,
            title=f"Capital project: {proposal.title}",
            amount_requested=proposal.amount,
            notes=f"From Development & Infrastructure (project: {proposal.project}).\n\n{proposal.summary}",
            document=proposal.document.name if proposal.document else "",
        )
        proposal.finance_proposal = finance_proposal
        proposal.status = CapitalProposal.Status.WITH_FINANCE
        proposal.save()
        log_event(
            AuditLog.Action.HANDOFF,
            request=request,
            obj=proposal,
            extra={"to": "finance", "proposal": finance_proposal.pk},
        )
    messages.success(request, "Sent to Finance. It now appears in Finance's appeals & proposals.")
    return redirect(resource.url("detail", proposal))


@never_cache
@portal_view(DEPT, level=MEMBER)
@require_POST
def cost_submit(request: HttpRequest, pk: int) -> HttpResponse:
    """Send a project cost (a draft Finance ledger entry) for executive approval (decisions 3 and 6)."""
    from django.core.exceptions import ValidationError

    from finance import services as finance_services

    resource, entry = post_action(request, DEPT, "project-costs", pk, "change")
    try:
        finance_services.submit(request, entry)
    except ValidationError as exc:
        messages.error(request, " ".join(exc.messages))
    else:
        messages.success(request, "Submitted. It now waits for executive approval before it is paid.")
    return redirect(resource.url("detail", entry))
