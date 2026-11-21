from django.urls import path, re_path

from portal.access import DEPARTMENT_ORDER

from . import approval_views, executive_views
from . import portal_views as views

app_name = "finance"
DEPT = "(?P<department>" + "|".join(DEPARTMENT_ORDER) + ")"

urlpatterns = [
    path("approvals/", approval_views.inbox, name="approvals"),
    path("executive/finance/", executive_views.executive_finance, name="executive_finance"),
    path("executive/finance/print/", executive_views.executive_finance_print, name="executive_finance_print"),
    path("approvals/<slug:kind>/<int:pk>/", approval_views.detail, name="approval_detail"),
    path("finance/budget/<int:pk>/submit/", views.budget_line_submit, name="budget_line_submit"),
    path("finance/ledger/<int:pk>/step/<slug:step>/", views.ledger_step, name="ledger_step"),
    path("finance/donations/<int:pk>/confirm/", views.donation_confirm, name="donation_confirm"),
    path("finance/financial-years/<int:pk>/close/", views.year_close, name="year_close"),
    path("finance/financial-years/<int:pk>/reopen/", views.year_reopen, name="year_reopen"),
    path("finance/partner-registrations/<int:pk>/to-donor/", views.enquiry_to_donor, name="enquiry_to_donor"),
    path(
        "finance/partner-registrations/<int:pk>/step/<slug:outcome>/",
        views.enquiry_outcome,
        name="enquiry_outcome",
    ),
    path("finance/volunteers/<int:pk>/step/<slug:step>/", views.volunteer_step, name="volunteer_step"),
    path("finance/donors/<int:pk>/accountability/", views.donor_report, name="donor_report"),
    # Every department's own budget (totals only).
    re_path(rf"^{DEPT}/my-budget/$", views.department_budget, name="department_budget"),
]
