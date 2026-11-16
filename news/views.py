from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Post


def post_list(request: HttpRequest) -> HttpResponse:
    qs = Post.objects.published()
    kind = request.GET.get("kind", "")
    if kind in Post.Kind.values:
        qs = qs.filter(kind=kind)
    page = Paginator(qs, 9).get_page(request.GET.get("page"))
    context = {"posts": page, "page_obj": page, "kinds": Post.Kind.choices, "kind": kind}
    return render(request, "news/list.html", context)


def post_detail(request: HttpRequest, slug: str) -> HttpResponse:
    post = get_object_or_404(Post.objects.published(), slug=slug)
    more = Post.objects.published().exclude(pk=post.pk)[:3]
    return render(request, "news/detail.html", {"post": post, "more": more})
