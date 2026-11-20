from django.urls import path

from . import portal_views as views

app_name = "logistics"

urlpatterns = [
    path("logistics/requests/<int:pk>/step/<slug:step>/", views.request_step, name="request_step"),
    path("logistics/requests/<int:pk>/recommend/", views.recommend, name="recommend"),
    path("logistics/orders/<int:pk>/receive/", views.receive, name="receive"),
    path(
        "logistics/event-logistics/<int:pk>/submit-budget/",
        views.plan_budget_submit,
        name="plan_budget_submit",
    ),
    path("finance/procurement/<int:pk>/confirm-budget/", views.confirm_budget, name="confirm_budget"),
]
