from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("2fa/verify/", views.verify_view, name="verify"),
    path("2fa/setup/", views.setup_view, name="setup"),
    path("2fa/backup-codes/", views.backup_codes_view, name="backup_codes"),
    path("2fa/backup-codes/regenerate/", views.regenerate_backup_codes_view, name="regenerate_backup_codes"),
    path("logout/", views.logout_view, name="logout"),
    path("invite/<str:token>/", views.accept_invite_view, name="accept_invite"),
]
