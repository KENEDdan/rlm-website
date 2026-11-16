"""Re-encrypt every encrypted column with the primary key and rebuild blind indexes.

Usage (see core/crypto.py and docs/DEPLOYMENT.md):
  1. Put the NEW Fernet key first in FIELD_ENCRYPTION_KEYS, keep the old key(s) after it, restart.
  2. ``python manage.py rotate_encryption_keys --dry-run`` then without ``--dry-run``.
  3. Remove the old key from FIELD_ENCRYPTION_KEYS and restart.

If BLIND_INDEX_KEY was changed, the same run recomputes every ``*_hash`` column from the decrypted value.
Everything runs in one transaction and aborts, writing nothing, if any value cannot be decrypted.
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core.management.base import BaseCommand, CommandError
from django.db import models, transaction

from audit.models import AuditLog
from audit.services import log_event
from core.crypto import DECRYPTION_FAILED, blind_index
from core.fields import encrypted_fields


def hash_pairs(model: type[models.Model], enc: list[str]) -> dict[str, str]:
    """``{"email_hash": "email", "donor_email_hash": "donor_email"}`` for blind-index columns."""
    names = {f.name for f in model._meta.concrete_fields}
    return {f"{src}_hash": src for src in enc if f"{src}_hash" in names}


class Command(BaseCommand):
    help = "Re-encrypt all encrypted fields with the first key in FIELD_ENCRYPTION_KEYS."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument("--dry-run", action="store_true", help="Decrypt everything, write nothing.")

    def handle(self, *args: Any, dry_run: bool = False, **options: Any) -> None:
        summary: dict[str, int] = {}
        with transaction.atomic():
            for model in apps.get_models():
                enc = encrypted_fields(model)
                if not enc:
                    continue
                pairs = hash_pairs(model, enc)
                count = 0
                for row in model._default_manager.values("pk", *enc).iterator(chunk_size=200):
                    if any(row[name] == DECRYPTION_FAILED for name in enc):
                        raise CommandError(
                            f"{model._meta.label} #{row['pk']} cannot be decrypted with the configured keys. "
                            "Add the missing old key to FIELD_ENCRYPTION_KEYS. Nothing was changed."
                        )
                    # update() runs get_prep_value -> fresh token under the primary key;
                    # it does not touch updated_at, so records keep their real modification time.
                    values = {name: row[name] for name in enc}
                    values.update({h: blind_index(row[src]) for h, src in pairs.items()})
                    if not dry_run:
                        model._default_manager.filter(pk=row["pk"]).update(**values)
                    count += 1
                summary[model._meta.label] = count
                self.stdout.write(f"{model._meta.label}: {count} row(s)")
            if dry_run:
                transaction.set_rollback(True)
        if not dry_run:
            log_event(AuditLog.Action.KEY_ROTATION, actor_email="system:manage.py", extra=summary)
        self.stdout.write(
            self.style.SUCCESS("Dry run OK: every row decrypts." if dry_run else "Rotation complete.")
        )
