"""Bootstrap the FIRST Super Admin: ``manage.py create_super_admin`` (interactive).

This is the only way to create an account outside the staff portal, and it refuses to run once an active
Super Admin exists: further Super Admins are invited by an existing one in the portal (with re-authentication,
the Super Admin limit and the audit log). The password is typed at a hidden prompt (never a command-line
argument) and must pass the password rules. Two-factor enrolment is forced at the first sign-in.
"""

from __future__ import annotations

import getpass
from typing import Any

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.core.validators import validate_email

from accounts.models import User
from accounts.services import AccountError, active_super_admins, bootstrap_super_admin


class Command(BaseCommand):
    help = "Create the first Super Admin (Founder). Refuses if an active Super Admin already exists."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--email", help="Asked interactively when omitted.")
        parser.add_argument("--name", help="Full name. Asked interactively when omitted.")

    def handle(self, *args: Any, email: str | None = None, name: str | None = None, **options: Any) -> None:
        if active_super_admins().exists():
            raise CommandError(
                "A Super Admin already exists. Additional Super Admins are invited by an existing Super Admin "
                "in the staff portal (Accounts > Invite a staff member)."
            )
        email = (email or input("Email: ")).strip().lower()
        try:
            validate_email(email)
        except ValidationError as exc:
            raise CommandError("That is not a valid email address.") from exc
        name = (name or input("Full name: ")).strip()
        if not name:
            raise CommandError("A name is required.")
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
        try:
            bootstrap_super_admin(email=email, full_name=name, password=password)
        except AccountError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            self.style.SUCCESS(f"Super Admin created for {email}.")
            + "\nNext: sign in NOW at the staff sign-in page. You must set up an authenticator app before "
            "anything else\n(whoever signs in first enrols the device). Keep the 10 backup codes safe."
        )
