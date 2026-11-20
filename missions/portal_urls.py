from django.urls import path

from . import portal_views as views

app_name = "missions"

urlpatterns = [
    path("missions/campaigns/<int:pk>/submit-budget/", views.budget_submit, name="budget_submit"),
]
