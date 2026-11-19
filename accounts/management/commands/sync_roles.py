from django.core.management.base import BaseCommand

from accounts.guard import sanctioned
from accounts.roles import sync_roles


class Command(BaseCommand):
    help = "Create/refresh staff role groups from accounts/roles.py (idempotent)."

    def handle(self, *args, **options):  # type: ignore[no-untyped-def]
        with sanctioned("system:sync_roles"):
            summary = sync_roles()
        for role, count in summary.items():
            self.stdout.write(f"{role}: {count} permissions")
