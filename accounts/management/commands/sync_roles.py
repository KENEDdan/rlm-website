from django.core.management.base import BaseCommand

from accounts.roles import sync_roles


class Command(BaseCommand):
    help = "Create/refresh staff role groups from accounts/roles.py (idempotent)."

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        for role, count in sync_roles().items():
            self.stdout.write(f"{role}: {count} permissions")
