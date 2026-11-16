"""Home and About pages (they pull from several apps)."""

from __future__ import annotations

from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from branches.models import Branch
from events.models import Event
from leadership.models import Leader
from news.models import Post
from programs.models import Program
from resources.models import Resource


def home(request: HttpRequest) -> HttpResponse:
    context = {
        "programs": Program.objects.published().filter(is_featured=True)[:6],
        "events": Event.objects.upcoming().select_related("branch")[:3],
        "posts": Post.objects.published()[:3],
        "branches": Branch.objects.published().select_related("country")[:6],
        "latest_sermon": Resource.objects.published().filter(kind="sermon").first(),
    }
    return render(request, "core/home.html", context)


def about(request: HttpRequest) -> HttpResponse:
    context = {
        "founder": Leader.objects.published().filter(role_title__icontains="founder").first(),
        "programs": Program.objects.published()[:6],
        "branches": Branch.objects.published().select_related("country"),
    }
    return render(request, "core/about.html", context)
