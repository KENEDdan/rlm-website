"""Reusable admin behaviour: role scoping, auditing, safe CSV export, 'mark handled'."""

from __future__ import annotations

import csv
from collections.abc import Iterable
from typing import Any

from django.contrib import admin, messages
from django.contrib.auth.models import Group, Permission
from django.db.models import Model, Q, QuerySet
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.utils import timezone

from accounts.roles import BRANCH_COORDINATOR, DEPARTMENT_HEAD, SCOPED_ROLES
from audit.models import AuditLog
from audit.services import log_event
from core.crypto import blind_index

CSV_INJECTION_PREFIXES = ("=", "+", "-", "@", "\t", "\r")


def csv_safe(value: Any) -> str:
    """Neutralise spreadsheet formula injection in exported cells."""
    text = "" if value is None else str(value)
    if text.startswith(CSV_INJECTION_PREFIXES):
        return "'" + text
    return text


def user_group_names(request: HttpRequest) -> set[str]:
    cached = getattr(request, "_rlm_groups", None)
    if cached is None:
        cached = set(request.user.groups.values_list("name", flat=True))
        request._rlm_groups = cached  # type: ignore[attr-defined]
    return cached


def has_unscoped_view(request: HttpRequest, model: type[Model]) -> bool:
    """True if any NON-scoped group (or a direct user permission) grants view on ``model``."""
    user = request.user
    if user.is_superuser:
        return True
    key = f"_rlm_unscoped_{model._meta.label_lower}"
    if hasattr(request, key):
        return getattr(request, key)
    codenames = [f"view_{model._meta.model_name}", f"change_{model._meta.model_name}"]
    perms = Permission.objects.filter(content_type__app_label=model._meta.app_label, codename__in=codenames)
    # Ask "does a NON-scoped group of this user hold the permission?" (filtering on Permission and
    # excluding by group name would wrongly drop perms shared with a scoped group).
    result = (
        Group.objects.filter(user=user, permissions__in=perms).exclude(name__in=SCOPED_ROLES).exists()
        or perms.filter(user=user).exists()
    )
    setattr(request, key, result)
    return result


class ScopedAdminMixin:
    """Restrict Branch Coordinators to their branch and Departmental Heads to their department.

    Set ``branch_lookup`` (e.g. ``"branch"`` or ``"event__branch"``) and/or ``department_lookup``.
    Applies to list views, object views (IDOR), change/delete permission, FK choices and new objects.
    """

    branch_lookup: str | None = None
    department_lookup: str | None = None

    def scope(self, request: HttpRequest, qs: QuerySet) -> QuerySet:
        if has_unscoped_view(request, self.model):  # type: ignore[attr-defined]
            return qs
        groups = user_group_names(request)
        user = request.user
        condition = Q(pk__in=[])
        if self.branch_lookup and BRANCH_COORDINATOR in groups and user.branch_id:
            condition |= Q(**{self.branch_lookup: user.branch_id})
        if self.department_lookup and DEPARTMENT_HEAD in groups and user.department_id:
            condition |= Q(**{self.department_lookup: user.department_id})
        return qs.filter(condition)

    def get_queryset(self, request: HttpRequest) -> QuerySet:
        return self.scope(request, super().get_queryset(request))  # type: ignore[misc]

    def _in_scope(self, request: HttpRequest, obj: Model | None) -> bool:
        if obj is None or obj.pk is None:
            return True
        return self.get_queryset(request).filter(pk=obj.pk).exists()

    def has_view_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return super().has_view_permission(request, obj) and self._in_scope(request, obj)  # type: ignore[misc]

    def has_change_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return super().has_change_permission(request, obj) and self._in_scope(request, obj)  # type: ignore[misc]

    def has_delete_permission(self, request: HttpRequest, obj: Model | None = None) -> bool:
        return super().has_delete_permission(request, obj) and self._in_scope(request, obj)  # type: ignore[misc]

    def _is_scoped(self, request: HttpRequest) -> bool:
        return not has_unscoped_view(request, self.model)  # type: ignore[attr-defined]

    def formfield_for_foreignkey(self, db_field: Any, request: HttpRequest, **kwargs: Any) -> Any:
        if self._is_scoped(request):
            user = request.user
            groups = user_group_names(request)
            if db_field.name == "branch" and BRANCH_COORDINATOR in groups:
                kwargs["queryset"] = db_field.related_model.objects.filter(pk=user.branch_id)
            elif db_field.name == "department" and DEPARTMENT_HEAD in groups:
                kwargs["queryset"] = db_field.related_model.objects.filter(pk=user.department_id)
            elif db_field.name == "event":
                from events.models import Event

                qs = Event.objects.all()
                cond = Q(pk__in=[])
                if BRANCH_COORDINATOR in groups:
                    cond |= Q(branch_id=user.branch_id)
                if DEPARTMENT_HEAD in groups:
                    cond |= Q(department_id=user.department_id)
                kwargs["queryset"] = qs.filter(cond)
        return super().formfield_for_foreignkey(db_field, request, **kwargs)  # type: ignore[misc]

    def save_model(self, request: HttpRequest, obj: Model, form: Any, change: bool) -> None:
        if self._is_scoped(request):
            groups = user_group_names(request)
            if (
                self.branch_lookup == "branch"
                and BRANCH_COORDINATOR in groups
                and not getattr(obj, "branch_id", None)
            ):
                obj.branch_id = request.user.branch_id  # type: ignore[attr-defined]
            if (
                self.department_lookup == "department"
                and DEPARTMENT_HEAD in groups
                and not getattr(obj, "department_id", None)
            ):
                obj.department_id = request.user.department_id  # type: ignore[attr-defined]
        super().save_model(request, obj, form, change)  # type: ignore[misc]


class AuditedAdminMixin:
    """Write every add/change/delete (and, for sensitive models, every view) to the audit log."""

    audit_views = False

    def log_addition(self, request: HttpRequest, obj: Model, message: Any) -> Any:
        log_event(AuditLog.Action.ADD, request=request, obj=obj)
        return super().log_addition(request, obj, message)  # type: ignore[misc]

    def log_change(self, request: HttpRequest, obj: Model, message: Any) -> Any:
        log_event(AuditLog.Action.CHANGE, request=request, obj=obj)
        return super().log_change(request, obj, message)  # type: ignore[misc]

    def log_deletions(self, request: HttpRequest, queryset: Iterable[Model]) -> Any:
        for obj in queryset:
            log_event(AuditLog.Action.DELETE, request=request, obj=obj)
        return super().log_deletions(request, queryset)  # type: ignore[misc]

    def change_view(
        self, request: HttpRequest, object_id: str, form_url: str = "", extra_context: Any = None
    ) -> HttpResponse:
        response = super().change_view(request, object_id, form_url, extra_context)  # type: ignore[misc]
        if self.audit_views and request.method == "GET" and response.status_code == 200:
            obj = self.get_object(request, object_id)  # type: ignore[attr-defined]
            if obj is not None:
                log_event(AuditLog.Action.VIEW, request=request, obj=obj)
        return response


class Echo:
    def write(self, value: str) -> str:
        return value


class ExportCsvMixin:
    """Admin action 'Export selected to CSV': needs ``<app>.export_<model>`` and is audit-logged."""

    export_fields: list[str] = []

    def has_export_permission(self, request: HttpRequest) -> bool:
        opts = self.model._meta  # type: ignore[attr-defined]
        return request.user.has_perm(f"{opts.app_label}.export_{opts.model_name}")

    @admin.action(description="Export selected to CSV", permissions=["export"])
    def export_csv(self, request: HttpRequest, queryset: QuerySet) -> StreamingHttpResponse:
        opts = self.model._meta  # type: ignore[attr-defined]
        fields = self.export_fields or [f.name for f in opts.concrete_fields]
        rows = queryset.order_by("pk")
        count = rows.count()
        log_event(
            AuditLog.Action.EXPORT,
            request=request,
            model=self.model,  # type: ignore[attr-defined]
            extra={"count": count, "fields": fields},
        )
        writer = csv.writer(Echo())

        def stream() -> Iterable[str]:
            yield writer.writerow(fields)
            for obj in rows.iterator():
                values = []
                for name in fields:
                    value = getattr(obj, name)
                    display = getattr(obj, f"get_{name}_display", None)
                    values.append(csv_safe(display() if callable(display) else value))
                yield writer.writerow(values)

        response = StreamingHttpResponse(stream(), content_type="text/csv; charset=utf-8")
        stamp = timezone.now().strftime("%Y%m%d-%H%M")
        response["Content-Disposition"] = f'attachment; filename="{opts.model_name}-{stamp}.csv"'
        response["Cache-Control"] = "no-store"
        return response


class SubmissionAdminMixin:
    """List/filter/'mark handled' plus email-hash search for encrypted submissions."""

    email_hash_field = "email_hash"

    @admin.action(description="Mark selected as handled", permissions=["change"])
    def mark_handled(self, request: HttpRequest, queryset: QuerySet) -> None:
        now = timezone.now()
        count = 0
        for obj in queryset:
            obj.status = "handled"
            obj.handled_by = request.user
            obj.handled_at = now
            obj.save(update_fields=["status", "handled_by", "handled_at", "updated_at"])
            log_event(AuditLog.Action.CHANGE, request=request, obj=obj, extra={"status": "handled"})
            count += 1
        messages.success(request, f"{count} item(s) marked as handled.")

    def get_search_results(
        self, request: HttpRequest, queryset: QuerySet, search_term: str
    ) -> tuple[QuerySet, bool]:
        """Encrypted fields can't be searched; an exact email is matched through its blind index."""
        term = search_term.strip()
        if "@" in term:
            return queryset.filter(**{self.email_hash_field: blind_index(term)}), False
        if term.isdigit():
            return queryset.filter(pk=int(term)), False
        return super().get_search_results(request, queryset, search_term)  # type: ignore[misc]
