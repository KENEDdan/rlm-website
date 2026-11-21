"""Website Administration (Technical Team) screens: /portal/website/..."""

from django.urls import path

from . import website_views as views

app_name = "website"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("vision-mission/", views.vision_mission, name="vision_mission"),
    path("vision-mission/new/", views.vm_create, name="vm_create"),
    path("vision-mission/<int:pk>/", views.vm_detail, name="vm_detail"),
    path("vision-mission/<int:pk>/rollback/", views.vm_rollback, name="vm_rollback"),
    path("hero/", views.hero, name="hero"),
    path("hero/preview/", views.hero_preview, name="hero_preview"),
    path("versions/", views.versions, name="versions"),
    path("versions/<int:pk>/restore/", views.version_restore, name="version_restore"),
]
