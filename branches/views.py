from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from events.models import Event

from .models import Branch, Country


def branch_list(request: HttpRequest) -> HttpResponse:
    countries = (
        Country.objects.filter(branches__is_published=True)
        .distinct()
        .prefetch_related(Prefetch("branches", queryset=Branch.objects.published(), to_attr="live_branches"))
    )
    return render(request, "branches/list.html", {"countries": countries})


def branch_detail(request: HttpRequest, slug: str) -> HttpResponse:
    branch = get_object_or_404(Branch.objects.published().select_related("country"), slug=slug)
    events = Event.objects.upcoming().filter(branch=branch)[:6]
    return render(request, "branches/detail.html", {"branch": branch, "events": events})
