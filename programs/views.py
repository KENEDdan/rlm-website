from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse, HttpResponsePermanentRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from events.models import Event

from .models import Activity, ActivityCategory

# Old programme slugs (before the four activity categories, D-035) -> the activity that replaced them.
OLD_PROGRAMME_SLUGS = {
    "youth-revival-conferences": "annual-youth-revival-conference",
    "prayer-and-intercession": "prayer-and-intercession",
    "discipleship": "mentorship-programme",
    "youth-and-leadership-development": "leadership-and-ministerial-trainings",
}


def _categories():  # type: ignore[no-untyped-def]
    activities = Activity.objects.published().prefetch_related("branches")
    return ActivityCategory.objects.published().prefetch_related(Prefetch("activities", queryset=activities))


def activity_list(request: HttpRequest) -> HttpResponse:
    return render(request, "activities/list.html", {"categories": _categories()})


def category_detail(request: HttpRequest, slug: str) -> HttpResponse:
    category = get_object_or_404(_categories(), slug=slug)
    return render(request, "activities/category.html", {"category": category})


def activity_detail(request: HttpRequest, slug: str) -> HttpResponse:
    activity = get_object_or_404(
        Activity.objects.published().select_related("category").prefetch_related("branches"), slug=slug
    )
    context = {
        "activity": activity,
        "events": Event.objects.upcoming().filter(activity=activity).select_related("branch")[:6],
        "related": Activity.objects.published()
        .filter(category=activity.category)
        .exclude(pk=activity.pk)[:3],
    }
    return render(request, "activities/detail.html", context)


def old_programme(request: HttpRequest, slug: str | None = None) -> HttpResponsePermanentRedirect:
    """/programs/... links (old bookmarks, search engines) go to the activities that replaced them."""
    target = OLD_PROGRAMME_SLUGS.get(slug or "")
    if target and Activity.objects.published().filter(slug=target).exists():
        return HttpResponsePermanentRedirect(reverse("programs:detail", args=[target]))
    return HttpResponsePermanentRedirect(reverse("programs:list"))
