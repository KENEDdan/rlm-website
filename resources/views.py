from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from core.form_views import is_htmx

from .models import Resource, ResourceCategory, Series


def resource_list(request: HttpRequest) -> HttpResponse:
    qs = Resource.objects.published().select_related("category", "series")
    kind = request.GET.get("kind", "")
    category = request.GET.get("category", "")
    series = request.GET.get("series", "")
    q = request.GET.get("q", "").strip()[:100]
    if kind in Resource.Kind.values:
        qs = qs.filter(kind=kind)
    if category:
        qs = qs.filter(category__slug=category)
    if series:
        qs = qs.filter(series__slug=series)
    if q:
        qs = qs.filter(
            Q(title__icontains=q)
            | Q(summary__icontains=q)
            | Q(speaker__icontains=q)
            | Q(scripture__icontains=q)
        )
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    context = {
        "resources": page,
        "page_obj": page,
        "kinds": Resource.Kind.choices,
        "categories": ResourceCategory.objects.all(),
        "series_list": Series.objects.all(),
        "filters": {"kind": kind, "category": category, "series": series, "q": q},
    }
    template = "resources/_results.html" if is_htmx(request) else "resources/list.html"
    return render(request, template, context)


def resource_detail(request: HttpRequest, slug: str) -> HttpResponse:
    resource = get_object_or_404(Resource.objects.published(), slug=slug)
    related = []
    if resource.series_id:
        related = Resource.objects.published().filter(series=resource.series).exclude(pk=resource.pk)[:4]
    return render(request, "resources/detail.html", {"resource": resource, "related": related})
