from django.urls import path, re_path

from portal.access import DEPARTMENT_ORDER

from . import portal_views as views

app_name = "finance"
DEPT = "(?P<department>" + "|".join(DEPARTMENT_ORDER) + ")"

urlpatterns = [
    path("finance/ledger/<int:pk>/step/<slug:step>/", views.ledger_step, name="ledger_step"),
    path("finance/donations/<int:pk>/confirm/", views.donation_confirm, name="donation_confirm"),
    path("finance/partner-registrations/<int:pk>/to-donor/", views.enquiry_to_donor, name="enquiry_to_donor"),
    path("finance/volunteers/<int:pk>/step/<slug:step>/", views.volunteer_step, name="volunteer_step"),
    path("finance/donors/<int:pk>/accountability/", views.donor_report, name="donor_report"),
    # Every department's own budget (totals only).
    re_path(rf"^{DEPT}/my-budget/$", views.department_budget, name="department_budget"),
]
