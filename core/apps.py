from django.apps import AppConfig
from django.contrib.admin.apps import AdminConfig


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"
    verbose_name = "Site"

    def ready(self) -> None:
        from django.db.models.signals import post_migrate

        from . import checks, signals  # noqa: F401
        from .site_text import ensure_defaults

        post_migrate.connect(ensure_defaults, sender=self, dispatch_uid="core.ensure_site_text_defaults")


class RLMAdminConfig(AdminConfig):
    default_site = "core.admin_site.RLMAdminSite"
