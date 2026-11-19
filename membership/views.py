from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .public_forms import MembershipRegistrationForm


@form_ratelimit
def register(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=MembershipRegistrationForm,
        template="membership/register.html",
        partial="membership/_register_form.html",
        success_message="Thank you for registering. Our membership team will review your application and contact you.",
        ack_template="membership_ack",
    )
