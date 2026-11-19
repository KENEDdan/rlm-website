from django.conf import settings
from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path
from django.views.decorators.cache import cache_page

from core import views as core_views
from core.sitemaps import SITEMAPS
from media_library import views as media_views

handler400 = "core.views.error_400"
handler403 = "core.views.error_403"
handler404 = "core.views.error_404"
handler500 = "core.views.error_500"

urlpatterns = [
    # Staff area: obscure, env-configured prefix. "/admin/" is deliberately NOT routed (404).
    path(f"{settings.ADMIN_URL}account/", include("accounts.urls")),
    path(settings.ADMIN_URL, admin.site.urls),
    path(settings.PORTAL_URL, include("portal.urls")),
    # Infrastructure
    path("healthz/", core_views.healthz, name="healthz"),
    path("robots.txt", core_views.robots_txt, name="robots_txt"),
    path("sitemap.xml", cache_page(60 * 60)(sitemap), {"sitemaps": SITEMAPS}, name="sitemap"),
    # Public site
    path("leadership/", include("leadership.urls")),
    path("programs/", include("programs.urls")),
    path("branches/", include("branches.urls")),
    path("events/", include("events.urls")),
    path("gallery/", include("media_library.urls")),
    path("testimonies/", media_views.testimonies, name="testimonies"),
    path("resources/", include("resources.urls")),
    path("news/", include("news.urls")),
    path("get-involved/", include("registrations.urls")),
    path("prayer/", include("prayer.urls")),
    path("contact/", include("contact.urls")),
    path("newsletter/", include("newsletter.urls")),
    path("", include("giving.urls")),
    path("", include("core.urls")),
]

if settings.DEBUG:
    from django.conf.urls.static import static

    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
