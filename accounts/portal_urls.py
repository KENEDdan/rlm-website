from django.urls import path

from . import portal_views as views

# Included inside the "portal" namespace at <PORTAL_URL>accounts/.
urlpatterns = [
    path("", views.users, name="users"),
    path("confirm/", views.reauth_view, name="reauth"),
    path("invite/", views.user_invite, name="user_invite"),
    path("review/", views.account_review, name="account_review"),
    path("audit/", views.audit_trail, name="audit_trail"),
    path("<int:pk>/", views.user_detail, name="user_detail"),
    path("<int:pk>/roles/", views.user_roles, name="user_roles"),
    path("<int:pk>/<slug:action>/", views.user_action, name="user_action"),
]
