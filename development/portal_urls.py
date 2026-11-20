from django.urls import path

from . import portal_views as views

app_name = "development"

urlpatterns = [
    path("development/capital-proposals/<int:pk>/send/", views.send_to_finance, name="send_to_finance"),
    path("development/project-costs/<int:pk>/submit/", views.cost_submit, name="cost_submit"),
]
