"""Break-glass: ``manage.py emergency_disable --email someone@example.org [--reset-2fa]``.

For when a Super Admin account itself is compromised (or no Super Admin can sign in) and the technical lead
must cut access from the server. It can only REMOVE access (deactivate, end sessions, optionally remove 2FA);
it can never grant anything. Every use is audit-logged and emailed to all active Super Admins.
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.guard import alert_super_admins, sanctioned
from accounts.models import Invitation, User
from accounts.services import kill_sessions
from accounts.twofactor import reset_two_factor


class Command(BaseCommand):
    help = "Emergency: deactivate one account and end its sessions (audited, Super Admins alerted)."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument(
            "--reset-2fa", action="store_true", help="Also remove the authenticator and backup codes."
        )

    def handle(self, *args: Any, email: str, reset_2fa: bool = False, **options: Any) -> None:
        user = User._base_manager.filter(email__iexact=email.strip()).first()
        if user is None:
            raise CommandError("No account with that email.")
        with transaction.atomic(), sanctioned("system:emergency_disable"):
            user.is_active = False
            user.deactivated_at = timezone.now()
            user.save()
            Invitation.objects.filter(user=user, used_at__isnull=True, revoked_at__isnull=True).update(
                revoked_at=timezone.now()
            )
            if reset_2fa:
                reset_two_factor(user)
        killed = kill_sessions(user)
        alert_super_admins(
            "The emergency_disable command was used on the server to deactivate a staff account. "
            "Check the account audit trail."
        )
        self.stdout.write(self.style.SUCCESS(f"Deactivated; {killed} session(s) ended."))
