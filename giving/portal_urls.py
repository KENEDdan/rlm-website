"""Bank and payment details (Finance head + Founder/Executive Director): /portal/finance/bank-details/..."""

from django.urls import path

from . import portal_views as views

app_name = "giving"

urlpatterns = [
    path("finance/bank-details/", views.bank_details, name="bank_details"),
    path("finance/bank-details/change/", views.bank_propose, name="bank_propose"),
    path("finance/bank-details/<int:pk>/", views.bank_change, name="bank_change"),
]
