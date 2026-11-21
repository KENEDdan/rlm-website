"""Home and About pages (they pull from several apps)."""

from __future__ import annotations

from django.db.models import Prefetch
from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from branches.models import Branch
from events.models import Event
from leadership.models import Leader
from media_library.models import Testimony
from news.models import Post
from programs.models import Activity, ActivityCategory

from .models import HERO_SLIDE_LIMIT, HeroSettings, HeroSlide, Partner

# Card carousels: enough to be worth swiping, small enough for slow connections (images are lazy).
CAROUSEL_LIMIT = 8


def activity_categories(*, featured: bool = False) -> list[ActivityCategory]:
    """Published categories, each with its published (optionally only featured) activities; empty ones hidden."""
    activities = Activity.objects.published()
    if featured:
        activities = activities.filter(is_featured=True)
    categories = ActivityCategory.objects.published().prefetch_related(
        Prefetch("activities", queryset=activities, to_attr="shown")
    )
    return [c for c in categories if c.shown]


def home(request: HttpRequest) -> HttpResponse:
    """Every section is a slider fed only by published/active/approved content; empty sections are hidden."""
    context = {
        "hero_slides": list(HeroSlide.objects.live()[:HERO_SLIDE_LIMIT]),
        "hero": HeroSettings.live(),
        "activity_categories": activity_categories(featured=True),
        "events": list(Event.objects.upcoming().select_related("branch")[:CAROUSEL_LIMIT]),
        "posts": list(Post.objects.published()[:CAROUSEL_LIMIT]),
        "branches": list(Branch.objects.published().select_related("country")),
        "testimonies": list(Testimony.objects.approved().select_related("branch")[:CAROUSEL_LIMIT]),
        "partners": list(Partner.objects.published()),
    }
    return render(request, "core/home.html", context)


def about(request: HttpRequest) -> HttpResponse:
    leaders = list(Leader.objects.published().select_related("branch"))
    context = {
        "founder": next((x for x in leaders if "founder" in x.role_title.lower()), None),
        "leaders": leaders,
        "activity_categories": activity_categories(),
        "branches": Branch.objects.published().select_related("country"),
    }
    return render(request, "core/about.html", context)
