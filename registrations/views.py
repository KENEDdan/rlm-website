from __future__ import annotations

from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .forms import VolunteerForm


@form_ratelimit
def volunteer(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=VolunteerForm,
        template="registrations/get_involved.html",
        partial="registrations/_volunteer_form.html",
        success_message="Thank you for offering to serve! Our team will be in touch soon.",
        ack_template="volunteer_ack",
    )
