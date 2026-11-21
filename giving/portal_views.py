"""Bank details in the staff portal: view (Finance head, Founder/Executive Director, Super Admin), propose, confirm."""

from __future__ import annotations

from django import forms
from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import urlencode
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods

from accounts import reauth
from audit.models import AuditLog
from audit.services import log_event
from portal.access import portal_view

from . import bank_details as svc
from .models import BANK_FIELDS, BankDetailChange, GivingSettings


class BankDetailsForm(forms.ModelForm):
    reason = forms.CharField(max_length=300, help_text="Why the details change, e.g. 'New account at ...'.")

    class Meta:
        model = BankDetailChange
        fields = list(BANK_FIELDS)
        widgets = {
            "transfer_instructions": forms.Textarea(attrs={"rows": 3}),
            "mobile_money_instructions": forms.Textarea(attrs={"rows": 3}),
        }


def _reauth(request: HttpRequest, back: str) -> HttpResponse:
    return redirect(f"{reverse('portal:reauth')}?{urlencode({'next': back})}")


@never_cache
@portal_view()
def bank_details(request: HttpRequest) -> HttpResponse:
    if not svc.can_view(request.user):
        raise PermissionDenied
    gs = GivingSettings.load()
    log_event(AuditLog.Action.VIEW, request=request, obj=gs, extra={"screen": "bank details"})
    context = {
        "gs": gs,
        "pending": svc.pending(),
        "history": BankDetailChange.objects.exclude(status="pending").select_related(
            "requested_by", "decided_by"
        )[:30],
        "can_propose": svc.can_propose(request.user),
        "can_confirm": svc.can_confirm(request.user),
    }
    return render(request, "portal/bank/details.html", context)


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def bank_propose(request: HttpRequest) -> HttpResponse:
    if not svc.can_propose(request.user):
        raise PermissionDenied
    back = reverse("portal:giving:bank_propose")
    if not reauth.is_fresh(request):  # password + 2FA before the form is even shown
        return _reauth(request, back)
    gs = GivingSettings.load()
    form = BankDetailsForm(request.POST or None, initial={f: getattr(gs, f) for f in BANK_FIELDS})
    if request.method == "POST" and form.is_valid():
        data = {f: form.cleaned_data[f] for f in BANK_FIELDS}
        try:
            svc.propose(request, data, form.cleaned_data["reason"])
        except svc.BankChangeError as exc:
            messages.error(request, str(exc))
        except reauth.ReauthRequired:
            return _reauth(request, back)
        else:
            messages.success(
                request,
                "Saved as a PENDING change. The Founder or Executive Director must confirm it before donors see it. "
                "An alert was emailed to the Finance head and the Founder.",
            )
            return redirect("portal:giving:bank_details")
    return render(request, "portal/bank/propose.html", {"form": form, "pending": svc.pending()})


@never_cache
@portal_view()
@require_http_methods(["GET", "POST"])
def bank_change(request: HttpRequest, pk: int) -> HttpResponse:
    if not svc.can_view(request.user):
        raise PermissionDenied
    change = get_object_or_404(BankDetailChange.objects.select_related("requested_by", "decided_by"), pk=pk)
    back = reverse("portal:giving:bank_change", args=[pk])
    if request.method == "POST":
        action = request.POST.get("action", "")
        try:
            if action == "confirm":
                svc.confirm(request, change)
                messages.success(request, "Confirmed. The new details are live on the Give page.")
            elif action == "reject":
                svc.reject(request, change, request.POST.get("note", ""))
                messages.success(request, "Rejected. The live details did not change.")
            elif action == "cancel":
                svc.cancel(request, change)
                messages.success(request, "Cancelled.")
            else:
                raise PermissionDenied
        except svc.BankChangeError as exc:
            messages.error(request, str(exc))
        except reauth.ReauthRequired:
            return _reauth(request, back)
        return redirect(back)
    log_event(AuditLog.Action.VIEW, request=request, obj=change)
    gs = GivingSettings.load()
    rows = [
        (BankDetailChange._meta.get_field(f).verbose_name, getattr(gs, f), getattr(change, f))
        for f in BANK_FIELDS
    ]
    context = {
        "change": change,
        "rows": rows,
        "can_confirm": svc.can_confirm(request.user) and change.requested_by_id != request.user.pk,
        "can_cancel": change.requested_by_id == request.user.pk or request.user.is_super_admin,
    }
    return render(request, "portal/bank/change.html", context)
