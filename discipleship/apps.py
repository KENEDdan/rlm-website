from django.apps import AppConfig


class DiscipleshipConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "discipleship"
    verbose_name = "Discipleship"

    def ready(self) -> None:
        from . import signals  # noqa: F401
