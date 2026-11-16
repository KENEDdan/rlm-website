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
