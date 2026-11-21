"""Version history and one-click rollback for website content (Technical Team models).

Every add / change / delete of a model in ``VERSIONED_MODELS`` - in the Django admin (``VersionedAdminMixin``)
or the portal - stores a ``ContentVersion`` snapshot of the record AFTER the change, plus an audit-log entry.
``restore`` puts a record back to an earlier snapshot (recreating it if it was deleted) and records that as a
new version, so a rollback can itself be rolled back.

Never versioned: Vision and Mission (they have their own approval history, ``ContentChangeRequest``), bank and
payment details, and anything personal. Files are stored by name: Django never deletes replaced files, so an
earlier version's photo is still there to restore.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from django.apps import apps
from django.contrib.contenttypes.models import ContentType
from django.db import models, transaction
from django.http import HttpRequest

from audit.models import AuditLog
from audit.services import log_event

from .models import ContentVersion

# Website content the Technical Team manages; every change is versioned.
VERSIONED_MODELS = [
    "core.sitecontent",
    "core.herosettings",
    "core.heroslide",
    "core.sociallink",
    "core.page",
    "core.pagetext",
    "core.partner",
    "programs.activitycategory",
    "programs.activity",
    "leadership.leader",
    "leadership.department",
    "branches.branch",
    "media_library.album",
]
# Fields a rollback never touches (they have their own controlled path).
NEVER_RESTORED = {
    "core.sitecontent": {"vision", "mission", "vision_mission_updated_at"},
    "programs.activity": {"department"},  # Super Admin only (restored only when a Super Admin rolls back)
    "core.herosettings": {"state"},
}
SKIP_FIELDS = {"id", "created_at", "updated_at"}


def is_versioned(model: type[models.Model] | models.Model) -> bool:
    return model._meta.label_lower in VERSIONED_MODELS


def _plain(value: Any) -> Any:
    if isinstance(value, datetime | date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, models.fields.files.FieldFile):
        return value.name or ""
    return value


def snapshot(obj: models.Model) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for field in obj._meta.concrete_fields:
        if field.name in SKIP_FIELDS:
            continue
        data[field.attname] = _plain(getattr(obj, field.attname))
    if obj.pk:
        for field in obj._meta.many_to_many:
            data[field.name] = sorted(getattr(obj, field.name).values_list("pk", flat=True))
    return data


def history(obj: models.Model) -> models.QuerySet:
    ct = ContentType.objects.get_for_model(obj, for_concrete_model=True)
    return ContentVersion.objects.filter(content_type=ct, object_id=str(obj.pk)).select_related("created_by")


def record(
    obj: models.Model,
    action: str,
    *,
    user: Any = None,
    request: HttpRequest | None = None,
    note: str = "",
) -> ContentVersion | None:
    if not is_versioned(obj):
        return None
    user = user if user is not None else getattr(request, "user", None)
    data = snapshot(obj)
    last = history(obj).first()
    changed = sorted(k for k, v in data.items() if last is None or last.data.get(k) != v)
    version = ContentVersion.objects.create(
        content_type=ContentType.objects.get_for_model(obj, for_concrete_model=True),
        object_id=str(obj.pk),
        object_repr=str(obj)[:200],
        action=action,
        data=data,
        changed_fields=changed,
        created_by=user if getattr(user, "is_authenticated", False) else None,
        note=note[:300],
    )
    return version


def can_restore(user: Any, version: ContentVersion) -> bool:
    model = version.content_type.model_class()
    if model is None or not is_versioned(model):
        return False
    opts = model._meta
    return bool(user.is_authenticated and user.has_perm(f"{opts.app_label}.change_{opts.model_name}"))


@transaction.atomic
def restore(version: ContentVersion, request: HttpRequest) -> models.Model:
    """Put the record back exactly as it was in ``version`` (one click), and record that as a new version."""
    user = request.user
    if not can_restore(user, version):
        raise PermissionError("You may not change this content.")
    model = version.content_type.model_class()
    label = model._meta.label_lower
    skip = set(NEVER_RESTORED.get(label, set()))
    if label == "programs.activity" and getattr(user, "is_super_admin", False):
        skip.discard("department")
    obj = model._default_manager.filter(pk=version.object_id).first()
    created = obj is None
    if created:
        obj = model(pk=version.object_id)
    m2m: dict[str, list[int]] = {}
    for key, value in version.data.items():
        if key in skip:
            continue
        try:
            field = model._meta.get_field(key)
        except Exception:  # noqa: BLE001 - attname of a FK (e.g. "category_id")
            field = next((f for f in model._meta.concrete_fields if f.attname == key), None)
        if field is None:
            continue  # the field no longer exists
        if field.many_to_many:
            m2m[field.name] = value
            continue
        if (
            field.is_relation
            and value is not None
            and not field.related_model._default_manager.filter(pk=value).exists()
        ):
            value = None if field.null else getattr(obj, field.attname, None)
        if isinstance(field, models.FileField):
            setattr(obj, field.attname, value)
            continue
        setattr(obj, field.attname, field.to_python(value) if value is not None else None)
    obj._rlm_rollback = True  # type: ignore[attr-defined]
    obj.save()
    for name, pks in m2m.items():
        getattr(obj, name).set(getattr(obj, name).model.objects.filter(pk__in=pks))
    record(
        obj,
        ContentVersion.Action.ROLLBACK,
        request=request,
        note=f"Restored version #{version.pk}",
    )
    log_event(
        AuditLog.Action.CHANGE,
        request=request,
        obj=obj,
        extra={"rollback_to_version": version.pk},
    )
    return obj


def model_for(label: str) -> type[models.Model]:
    return apps.get_model(label)


class VersionedAdminMixin:
    """Admin mixin: every save and delete of a versioned model leaves a ContentVersion."""

    def save_model(self, request: HttpRequest, obj: models.Model, form: Any, change: bool) -> None:
        super().save_model(request, obj, form, change)  # type: ignore[misc]
        self._pending_version = (obj, change)

    def save_related(self, request: HttpRequest, form: Any, formsets: Any, change: bool) -> None:
        super().save_related(request, form, formsets, change)  # type: ignore[misc]
        pending = getattr(self, "_pending_version", None)
        if pending is not None:  # after many-to-many fields are saved, so the snapshot is complete
            obj, was_change = pending
            record(
                obj,
                (ContentVersion.Action.CHANGE if was_change else ContentVersion.Action.ADD),
                request=request,
            )
            self._pending_version = None

    def delete_model(self, request: HttpRequest, obj: models.Model) -> None:
        record(obj, ContentVersion.Action.DELETE, request=request)
        super().delete_model(request, obj)  # type: ignore[misc]

    def delete_queryset(self, request: HttpRequest, queryset: models.QuerySet) -> None:
        for obj in queryset:
            record(obj, ContentVersion.Action.DELETE, request=request)
        super().delete_queryset(request, queryset)  # type: ignore[misc]
