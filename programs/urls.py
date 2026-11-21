from django.urls import path

from . import views

app_name = "programs"

urlpatterns = [
    path("", views.activity_list, name="list"),
    path("category/<slug:slug>/", views.category_detail, name="category"),
    path("<slug:slug>/", views.activity_detail, name="detail"),
]

# Mounted at /programs/: permanent redirects from the old programme pages.
old_urlpatterns = [
    path("", views.old_programme),
    path("<slug:slug>/", views.old_programme),
]
