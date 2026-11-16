from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse

from core.models import SiteSettings

from .models import Subscriber


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=5)
def send_confirmation(pk: int) -> bool:
    from .services import make_confirm_token, make_unsubscribe_token

    sub = Subscriber.objects.filter(pk=pk, status=Subscriber.Status.PENDING).first()
    if sub is None:
        return False
    site = SiteSettings.load()
    unsubscribe_url = settings.SITE_URL + reverse(
        "newsletter:unsubscribe", args=[make_unsubscribe_token(sub)]
    )
    context = {
        "site": site,
        "confirm_url": settings.SITE_URL + reverse("newsletter:confirm", args=[make_confirm_token(sub)]),
        "unsubscribe_url": unsubscribe_url,
    }
    message = EmailMultiAlternatives(
        subject=f"Please confirm your subscription to {site.ministry_name}",
        body=render_to_string("emails/newsletter_confirm.txt", context),
        from_email=settings.DEFAULT_FROM_EMAIL,
        to=[sub.email],
        headers={"List-Unsubscribe": f"<{unsubscribe_url}>"},
    )
    message.send()
    return True
