from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from core.crypto import blind_index
from core.form_views import handle_public_form
from core.ratelimit import form_ratelimit
from registrations.forms import EventRegistrationForm
from registrations.models import EventRegistration

from .models import Event


def event_list(request: HttpRequest) -> HttpResponse:
    events = Event.objects.upcoming().select_related("branch", "activity")
    return render(request, "events/list.html", {"events": events, "showing": "upcoming"})


def past_events(request: HttpRequest) -> HttpResponse:
    page = Paginator(Event.objects.past().select_related("branch"), 12).get_page(request.GET.get("page"))
    return render(request, "events/list.html", {"events": page, "page_obj": page, "showing": "past"})


def event_detail(request: HttpRequest, slug: str) -> HttpResponse:
    event = get_object_or_404(Event.objects.published().select_related("branch", "activity"), slug=slug)
    return render(
        request, "events/detail.html", {"event": event, "albums": event.albums.filter(is_published=True)}
    )


def _save_registration(event: Event):  # type: ignore[no-untyped-def]
    def _save(form: EventRegistrationForm) -> EventRegistration | None:
        # Lock the event row so two people can't take the last seat at the same time.
        locked = Event.objects.select_for_update().get(pk=event.pk)
        email_hash = blind_index(form.cleaned_data["email"])
        if EventRegistration.objects.filter(event=locked, email_hash=email_hash).exists():
            return None  # duplicate: same success message, no second record, no enumeration
        attendees = form.cleaned_data.get("attendees") or 1
        if not locked.can_register or (locked.spots_left is not None and attendees > locked.spots_left):
            raise ValidationError("Sorry, the event just became full.")
        registration = form.save(commit=False)
        registration.event = locked
        registration.consent = True
        registration.save()
        return registration

    return _save


@form_ratelimit
def register(request: HttpRequest, slug: str) -> HttpResponse:
    event = get_object_or_404(Event.objects.published(), slug=slug)
    if not event.can_register:
        return render(request, "events/register_closed.html", {"event": event}, status=200)
    try:
        with transaction.atomic():
            return handle_public_form(
                request,
                form_class=EventRegistrationForm,
                form_kwargs={"event": event},
                template="events/register.html",
                partial="events/_register_form.html",
                success_message=f"You're registered for {event.title}. A confirmation email is on its way.",
                ack_template="event_registration_ack",
                save=_save_registration(event),
                context={"event": event},
                success_redirect=event.get_absolute_url(),
            )
    except ValidationError:  # raised by _save when the last seat was just taken
        return render(request, "events/register_closed.html", {"event": event})
