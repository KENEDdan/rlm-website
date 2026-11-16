from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render
from django.views.decorators.http import require_http_methods

from core.form_views import is_htmx
from core.ratelimit import form_ratelimit

from . import services
from .forms import SubscribeForm

DONE = "Thank you! Please check your inbox and click the link to confirm your subscription."


@form_ratelimit
@require_http_methods(["GET", "POST"])
def subscribe(request: HttpRequest) -> HttpResponse:
    form = SubscribeForm(request.POST or None, request=request)
    if request.method == "POST" and form.is_valid():
        services.subscribe(form.cleaned_data["email"], form.cleaned_data.get("name", ""))
        # Same message whether or not the address was already subscribed (no enumeration).
        if is_htmx(request):
            return render(request, "includes/form_success.html", {"message": DONE})
        return render(request, "newsletter/status.html", {"title": "Almost there", "message": DONE})
    template = "newsletter/_form.html" if is_htmx(request) else "newsletter/subscribe.html"
    return render(request, template, {"form": form})


def confirm(request: HttpRequest, token: str) -> HttpResponse:
    sub = services.confirm(token)
    if sub is None:
        return render(
            request,
            "newsletter/status.html",
            {
                "title": "Link expired",
                "message": "This confirmation link is invalid or has expired. Please subscribe again.",
            },
            status=400,
        )
    return render(
        request,
        "newsletter/status.html",
        {"title": "Subscribed", "message": "Your subscription is confirmed. Welcome!"},
    )


@require_http_methods(["GET", "POST"])
def unsubscribe(request: HttpRequest, token: str) -> HttpResponse:
    sub = services.subscriber_from_unsubscribe_token(token)
    if sub is None:
        return render(
            request,
            "newsletter/status.html",
            {"title": "Invalid link", "message": "This unsubscribe link is not valid."},
            status=400,
        )
    if request.method == "POST":  # GET only shows a button, so email scanners can't unsubscribe people
        services.unsubscribe(sub)
        return render(
            request,
            "newsletter/status.html",
            {"title": "Unsubscribed", "message": "You will not receive any more emails from us."},
        )
    return render(request, "newsletter/unsubscribe.html", {"token": token})
