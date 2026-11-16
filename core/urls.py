from django.urls import path

from . import pages, views

app_name = "core"

urlpatterns = [
    path("", pages.home, name="home"),
    path("about/", pages.about, name="about"),
    path("privacy/", views.page_detail, {"slug": "privacy"}, name="privacy"),
    path("terms/", views.page_detail, {"slug": "terms"}, name="terms"),
    path("pages/<slug:slug>/", views.page_detail, name="page"),
]
