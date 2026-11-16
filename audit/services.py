from __future__ import annotations

from typing import Any

from django.db import models
from django.http import HttpRequest

from .models import AuditLog


def _client(request: HttpRequest | None) -> tuple[str | None, str]:
    if request is None:
        return None, ""
    return request.META.get("REMOTE_ADDR") or None, request.META.get("HTTP_USER_AGENT", "")[:200]


def safe_repr(obj: models.Model) -> str:
    """Use the model's non-PII label when it defines one (sensitive models do)."""
    label = getattr(obj, "audit_label", None)
    if label:
        return str(label)[:200]
    return f"{obj._meta.verbose_name} #{obj.pk}"[:200]


def log_event(
    action: str,
    *,
    request: HttpRequest | None = None,
    user: Any = None,
    obj: models.Model | None = None,
    model: type[models.Model] | None = None,
    actor_email: str = "",
    extra: dict[str, Any] | None = None,
) -> AuditLog:
    user = user if user is not None else getattr(request, "user", None)
    actor_id = getattr(user, "pk", None) if getattr(user, "is_authenticated", False) else None
    email = actor_email or (getattr(user, "email", "") if actor_id else "")
    ip, ua = _client(request)
    meta_model = obj.__class__ if obj is not None else model
    return AuditLog.objects.create(
        actor_id=actor_id,
        actor_email=email[:254],
        action=action,
        app_label=meta_model._meta.app_label if meta_model else "",
        model=meta_model._meta.model_name if meta_model else "",
        object_id=str(obj.pk) if obj is not None and obj.pk is not None else "",
        object_repr=safe_repr(obj) if obj is not None else "",
        ip_address=ip,
        user_agent=ua,
        extra=extra or {},
    )
