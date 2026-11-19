"""Bulk member emails, one message per person (no one sees another recipient's address)."""

from __future__ import annotations

from celery import shared_task
from django.conf import settings
from django.core.mail import send_mail
from django.template.loader import render_to_string

from core.models import SiteSettings

from .models import BulkMessage, Member


@shared_task(autoretry_for=(OSError,), retry_backoff=True, max_retries=3)
def send_bulk_message(message_pk: int, member_ids: list[int]) -> int:
    message = BulkMessage.objects.filter(pk=message_pk).first()
    if message is None:
        return 0
    site = SiteSettings.load()
    sent = 0
    for member in Member.objects.filter(pk__in=member_ids, comms_opt_in=True, is_minor=False):
        if not member.email:
            continue
        body = render_to_string(
            "emails/member_bulk.txt", {"message": message, "member": member, "site": site}
        )
        send_mail(message.subject, body, settings.DEFAULT_FROM_EMAIL, [member.email])
        sent += 1
    return sent
