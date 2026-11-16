from django.urls import path

from . import views

app_name = "media_library"

urlpatterns = [
    path("", views.gallery, name="gallery"),
    path("videos/", views.videos, name="videos"),
    path("reports/", views.reports, name="reports"),
    path("<slug:slug>/", views.album_detail, name="album"),
]
