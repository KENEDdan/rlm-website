from django.apps import apps
from django.urls import include, path, re_path
from django.utils.module_loading import module_has_submodule

from . import print_views, retention_views, target_views, views
from .access import DEPARTMENT_ORDER

app_name = "portal"

DEPT = "(?P<department>" + "|".join(DEPARTMENT_ORDER) + ")"
SLUG = r"(?P<slug>[a-z0-9-]+)"
PK = r"(?P<pk>\d+)"


def department_workflow_urls() -> list:
    """Each department app may add workflow URLs (approve, post, hand off…) in its portal_urls.py."""
    patterns = []
    for config in apps.get_app_configs():
        if config.name != "accounts" and module_has_submodule(config.module, "portal_urls"):
            patterns.append(path("", include(f"{config.name}.portal_urls")))
    return patterns


urlpatterns = [
    path("", views.home, name="home"),
    path("no-access/", views.no_access, name="no_access"),
    path("executive/", views.executive, name="executive"),
    path("executive/print/", print_views.executive_print, name="executive_print"),
    path("retention/", retention_views.retention_screen, name="retention"),
    path("targets/", target_views.target_list, name="targets"),
    path("targets/new/", target_views.target_create, name="target_create"),
    path("targets/import/", target_views.target_import, name="target_import"),
    path("targets/print/", print_views.targets_print, name="targets_print"),
    path("targets/template.csv", target_views.target_template, name="target_template"),
    path("targets/<int:pk>/", target_views.target_detail, name="target_detail"),
    path("accounts/", include("accounts.portal_urls")),
    path("website/", include("portal.website_urls")),
    *department_workflow_urls(),
    re_path(rf"^{DEPT}/$", views.dashboard, name="dashboard"),
    re_path(rf"^{DEPT}/screens/$", views.department_resources, name="department_resources"),
    re_path(rf"^{DEPT}/export/(?P<fmt>csv)/$", views.dashboard_export, name="dashboard_export"),
    re_path(rf"^{DEPT}/print/$", print_views.dashboard_print, name="dashboard_print"),
    re_path(rf"^{DEPT}/reports/{PK}/print/$", print_views.report_print, name="report_print"),
    re_path(rf"^{DEPT}/reports/generate/$", views.report_generate, name="report_generate"),
    re_path(rf"^{DEPT}/reports/{PK}/submit/$", views.report_submit, name="report_submit"),
    re_path(rf"^{DEPT}/reports/{PK}/review/$", views.report_review, name="report_review"),
    re_path(rf"^{DEPT}/{SLUG}/$", views.resource_list, name="resource_list"),
    re_path(rf"^{DEPT}/{SLUG}/new/$", views.resource_form, name="resource_create"),
    re_path(rf"^{DEPT}/{SLUG}/export\.csv$", views.resource_export, name="resource_export"),
    re_path(rf"^{DEPT}/{SLUG}/print/$", print_views.resource_print, name="resource_print"),
    re_path(rf"^{DEPT}/{SLUG}/{PK}/$", views.resource_detail, name="resource_detail"),
    re_path(rf"^{DEPT}/{SLUG}/{PK}/edit/$", views.resource_form, name="resource_edit"),
    re_path(rf"^{DEPT}/{SLUG}/{PK}/delete/$", views.resource_delete, name="resource_delete"),
    re_path(rf"^{DEPT}/{SLUG}/{PK}/file/(?P<field>[a-z_]+)/$", views.resource_file, name="resource_file"),
]
