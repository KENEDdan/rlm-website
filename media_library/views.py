from django.core.paginator import Paginator
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render

from .models import Album, Report, Testimony, Video


def gallery(request: HttpRequest) -> HttpResponse:
    albums = Paginator(Album.objects.published().prefetch_related("photos"), 12).get_page(
        request.GET.get("page")
    )
    videos = Video.objects.published()[:3]
    return render(
        request, "media_library/gallery.html", {"albums": albums, "page_obj": albums, "videos": videos}
    )


def album_detail(request: HttpRequest, slug: str) -> HttpResponse:
    album = get_object_or_404(Album.objects.published(), slug=slug)
    photos = album.photos.filter(is_published=True)
    context = {"album": album, "photos": photos, "videos": album.videos.published()}
    return render(request, "media_library/album.html", context)


def videos(request: HttpRequest) -> HttpResponse:
    page = Paginator(Video.objects.published(), 12).get_page(request.GET.get("page"))
    return render(request, "media_library/videos.html", {"videos": page, "page_obj": page})


def reports(request: HttpRequest) -> HttpResponse:
    return render(request, "media_library/reports.html", {"reports": Report.objects.published()})


def testimonies(request: HttpRequest) -> HttpResponse:
    items = Testimony.objects.published().filter(consent_confirmed=True)
    page = Paginator(items, 10).get_page(request.GET.get("page"))
    return render(request, "media_library/testimonies.html", {"testimonies": page, "page_obj": page})
