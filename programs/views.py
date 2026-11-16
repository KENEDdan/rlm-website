from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from events.models import Event

from .models import Program


def program_list(request: HttpRequest) -> HttpResponse:
    return render(request, "programs/list.html", {"programs": Program.objects.published()})


def program_detail(request: HttpRequest, slug: str) -> HttpResponse:
    program = get_object_or_404(Program.objects.published(), slug=slug)
    events = Event.objects.upcoming().filter(program=program)[:6]
    return render(request, "programs/detail.html", {"program": program, "events": events})
