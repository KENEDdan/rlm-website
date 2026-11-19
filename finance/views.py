from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .public_forms import FinanceVolunteerForm


@form_ratelimit
def volunteer(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=FinanceVolunteerForm,
        template="finance/volunteer.html",
        partial="finance/_volunteer_form.html",
        success_message="Thank you for offering to serve. Our Finance team will review your application and contact you.",
        ack_template="finance_volunteer_ack",
    )
