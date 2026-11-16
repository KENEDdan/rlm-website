from django.urls import path

from . import views

app_name = "giving"

urlpatterns = [
    path("give/", views.give, name="give"),
    path("give/pledge/", views.pledge, name="pledge"),
    path("partner/", views.partner, name="partner"),
    path("payments/webhook/<slug:provider>/", views.webhook, name="webhook"),
]
