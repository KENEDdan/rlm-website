"""One code path for every public form: validate -> save -> alert staff -> acknowledge -> PRG.

Works without JavaScript (normal POST + redirect). With HTMX (``HX-Request`` header) only the form
partial is returned, so the page does not reload.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from django.contrib import messages
from django.db import transaction
from django.db.models import Model
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from .tasks import notify_staff_new_submission, send_acknowledgement


def is_htmx(request: HttpRequest) -> bool:
    return request.headers.get("HX-Request") == "true"


def queue_notifications(obj: Model, ack_template: str | None, email_field: str = "email") -> None:
    label = obj._meta.label
    pk = obj.pk

    def _send() -> None:
        notify_staff_new_submission.delay(label, pk)
        if ack_template and getattr(obj, email_field, ""):
            send_acknowledgement.delay(label, pk, ack_template, email_field)

    transaction.on_commit(_send)


def handle_public_form(
    request: HttpRequest,
    *,
    form_class: type,
    template: str,
    partial: str,
    success_message: str,
    ack_template: str | None = None,
    email_field: str = "email",
    form_kwargs: dict[str, Any] | None = None,
    save: Callable[[Any], Model | None] | None = None,
    context: dict[str, Any] | None = None,
    success_redirect: str | None = None,
) -> HttpResponse:
    form = form_class(request.POST or None, request=request, **(form_kwargs or {}))
    ctx = {"form": form, **(context or {})}
    if request.method == "POST":
        if form.is_valid():
            with transaction.atomic():
                obj = save(form) if save else form.save()
                if obj is not None:
                    queue_notifications(obj, ack_template, email_field)
            if is_htmx(request):
                return render(request, "includes/form_success.html", {"message": success_message})
            messages.success(request, success_message)
            return redirect(success_redirect or request.path)
        if is_htmx(request):
            return render(request, partial, ctx, status=200)
    return render(request, template, ctx)
