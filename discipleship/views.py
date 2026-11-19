from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .public_forms import DiscipleshipRegistrationForm


@form_ratelimit
def register(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=DiscipleshipRegistrationForm,
        template="discipleship/register.html",
        partial="discipleship/_register_form.html",
        success_message="Thank you for registering for discipleship. Our team will contact you about a class.",
        ack_template="discipleship_ack",
    )
