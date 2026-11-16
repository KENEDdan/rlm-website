"""Create the Founder account: ``manage.py create_founder --email founder@ministry.org --name "Full Name"``.

Unlike ``createsuperuser`` it also adds the Founder role, enforces the password rules, and records the
creation in the audit log. The Founder then signs in once to enrol the authenticator app (mandatory 2FA).
"""

from __future__ import annotations

import getpass
from typing import Any

from django.contrib.auth.models import Group
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email
from django.db import transaction

from accounts.models import User
from accounts.roles import FOUNDER
from audit.models import AuditLog
from audit.services import log_event


class Command(BaseCommand):
    help = (
        "Create the Founder / Super Admin account (asks for the password; never pass it on the command line)."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", required=True)
        parser.add_argument("--name", required=True, help="Full name")

    def handle(self, *args: Any, email: str, name: str, **options: Any) -> None:
        email = email.strip().lower()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("That is not a valid email address.") from exc
        if User.objects.filter(email__iexact=email).exists():
            raise CommandError("An account with this email already exists. Use the admin to change it.")
        candidate = User(email=email, full_name=name)
        for _attempt in range(3):
            password = getpass.getpass("Password (12+ characters, mixed): ")
            if password != getpass.getpass("Password again: "):
                self.stderr.write("The passwords do not match.")
                continue
            try:
                validate_password(password, user=candidate)
            except ValidationError as exc:
                self.stderr.write(" ".join(exc.messages))
                continue
            break
        else:
            raise CommandError("No valid password given. Nothing was created.")
        with transaction.atomic():
            user = User.objects.create_superuser(email=email, password=password, full_name=name)
            user.groups.add(Group.objects.get(name=FOUNDER))
            log_event(AuditLog.Action.ADD, obj=user, actor_email="system:create_founder")
        self.stdout.write(
            self.style.SUCCESS(f"Founder account created for {email}.")
            + "\nNext: sign in NOW at the staff sign-in page and scan the QR code with an authenticator app"
            "\n(whoever signs in first sets up the two-factor device). Keep the 10 backup codes safe."
        )
