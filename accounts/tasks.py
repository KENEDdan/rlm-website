"""Scheduled account checks (Celery beat): integrity fingerprint and dormant accounts."""

from __future__ import annotations

from celery import shared_task

from .guard import alert_super_admins
from .integrity import check_integrity
from .services import dormant_sweep


@shared_task
def account_integrity_check() -> bool:
    return check_integrity()


@shared_task
def dormant_accounts() -> dict[str, int]:
    result = dormant_sweep()
    if result["flagged"] or result["disabled"]:
        alert_super_admins(
            f"Dormant staff accounts: {result['flagged']} newly flagged (unused for a long time) and "
            f"{result['disabled']} disabled automatically. Review them under Accounts > Access review."
        )
    return result
