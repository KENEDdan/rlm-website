from django.core.cache import cache
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import SITE_SETTINGS_CACHE_KEY, Page, SocialLink


@receiver(post_delete, sender=SocialLink)
def _clear_social_cache(**kwargs: object) -> None:
    cache.delete(SITE_SETTINGS_CACHE_KEY + ":social")


@receiver(post_delete, sender=Page)
def _clear_footer_pages_cache(**kwargs: object) -> None:
    cache.delete(SITE_SETTINGS_CACHE_KEY + ":footer-pages")


# ------------------------------------------------------------------ application retention (ministry decision 8)
def _application_pre_save(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    from .retention import sync_outcome

    sync_outcome(instance)


def _application_post_save(sender, instance, **kwargs):  # type: ignore[no-untyped-def]
    if getattr(instance, "_count_success", False):
        from .retention import OUTCOME, count, spec_for

        instance._count_success = False
        spec = spec_for(instance)
        if spec is not None:
            count(spec, instance, OUTCOME.SUCCESSFUL)


def connect_application_signals() -> None:
    from django.db.models.signals import post_save, pre_save

    from .retention import SPECS

    for spec in SPECS.values():
        pre_save.connect(
            _application_pre_save, sender=spec.model_label, dispatch_uid=f"retention-pre-{spec.code}"
        )
        post_save.connect(
            _application_post_save, sender=spec.model_label, dispatch_uid=f"retention-post-{spec.code}"
        )


connect_application_signals()
