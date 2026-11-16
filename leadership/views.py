from django.http import HttpRequest, HttpResponse
from django.shortcuts import render

from .models import Leader


def leadership(request: HttpRequest) -> HttpResponse:
    leaders = Leader.objects.published().select_related("department", "branch")
    return render(request, "leadership/list.html", {"leaders": leaders})
