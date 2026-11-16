from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Site"

    def ready(self) -> None:
        from . import checks, signals  # noqa: F401


class RLMAdminConfig(AdminConfig):
    default_site = "core.admin_site.RLMAdminSite"
