from django.http import HttpRequest, HttpResponse

from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit

from .forms import PrayerRequestForm


@form_ratelimit
def prayer_request(request: HttpRequest) -> HttpResponse:
    return handle_public_form(
        request,
        form_class=PrayerRequestForm,
        template="prayer/prayer.html",
        partial="prayer/_form.html",
        success_message="Your prayer request has been received. We are standing with you in prayer.",
        ack_template="prayer_ack",
    )
