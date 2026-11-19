from django.apps import AppConfig


class PortalConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "portal"
    verbose_name = "Staff portal"

    def ready(self) -> None:
        from django.utils.module_loading import autodiscover_modules

        from . import signals  # noqa: F401

        # Each department app declares its screens and dashboard in portal_config.py.
        autodiscover_modules("portal_config")
