from django.urls import path

from . import portal_views as views

app_name = "communications"

urlpatterns = [
    path("media/testimonies/<int:pk>/approval/", views.testimony_approval, name="testimony_approval"),
]
