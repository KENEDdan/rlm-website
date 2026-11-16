from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .forms import ContactForm


@form_ratelimit
def contact(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=ContactForm,
        template="contact/contact.html",
        partial="contact/_form.html",
        success_message="Thank you for your message. We will reply as soon as we can.",
        ack_template="contact_ack",
    )
