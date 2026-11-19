from __future__ import annotations

import logging

from django.db import transaction
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from . import services
from .forms import PartnershipForm, PledgeForm
from .models import CurrentNeed, Donation, GivingCategory, GivingSettings, PartnershipEnquiry
from .providers import get_provider
from .providers.base import WebhookSignatureError
from .providers.manual import ManualBankTransfer

logger = logging.getLogger(__name__)


def _giving_context() -> dict:
    return {
        "giving": GivingSettings.load(),
        "categories": GivingCategory.objects.filter(is_active=True),
        "needs": CurrentNeed.objects.filter(is_published=True)[:6],
    }


def give(request: HttpRequest) -> HttpResponse:
    return render(request, "giving/give.html", {**_giving_context(), "form": PledgeForm(request=request)})


def _save_pledge(form: PledgeForm) -> Donation:
    donation = form.save(commit=False)
    donation.provider = Donation.Provider.MANUAL_BANK
    donation.status = Donation.Status.PLEDGED
    donation.save()
    ManualBankTransfer().start_checkout(donation, request=None)  # type: ignore[arg-type]
    return donation


@form_ratelimit
def pledge(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=PledgeForm,
        template="giving/pledge.html",
        partial="giving/_pledge_form.html",
        success_message=(
            "Thank you for your generosity! Our finance team will confirm your gift and, if you gave an email, "
            "send you a receipt."
        ),
        ack_template="pledge_ack",
        email_field="donor_email",
        save=_save_pledge,
        context=_giving_context(),
    )


def _save_partner(form: PartnershipForm) -> PartnershipEnquiry:
    """Save the registration and put it straight into Finance's donor/partner pipeline as a prospect."""
    from finance.services import donor_from_enquiry

    enquiry = form.save()
    donor_from_enquiry(enquiry)
    return enquiry


@form_ratelimit
def partner(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=PartnershipForm,
        save=_save_partner,
        template="giving/partner.html",
        partial="giving/_partner_form.html",
        success_message="Thank you for registering as a partner. Our team will be in touch soon.",
        ack_template="partnership_ack",
        context=_giving_context(),
    )


@csrf_exempt  # authenticated by the gateway's HMAC signature instead of a CSRF token
@require_POST
def webhook(request: HttpRequest, provider: str) -> HttpResponse:
    if not GivingSettings.load().gateway_enabled:
        raise Http404
    try:
        handler = get_provider(provider)
    except LookupError as exc:
        raise Http404 from exc
    if not handler.supports_webhooks:
        raise Http404
    try:
        outcome = handler.verify_webhook(request)
    except WebhookSignatureError:
        logger.warning("Rejected webhook with invalid signature for provider %s", provider)
        return JsonResponse({"error": "invalid signature"}, status=400)
    # Record + apply in ONE transaction: if applying fails, nothing is stored, the gateway's retry is
    # processed normally instead of being swallowed as a "duplicate".
    with transaction.atomic():
        event, created = services.record_webhook(provider, outcome, request.body)
        if not event.processed:  # also re-applies events stored unprocessed by older code
            services.apply_webhook(event, outcome)
    return JsonResponse({"received": True, "duplicate": not created})
