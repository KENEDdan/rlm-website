"""Declarative portal 'resources': one class per model describes its list, form, detail page and rules.

The generic views in ``portal.views`` use these for every department, so scoping is written ONCE:

* ``get_queryset(access)``: department level -> branch restriction -> resource ``scope()`` hook. Every list,
  detail, edit, delete, file download and CSV export starts from it (no IDOR: an object outside the
  queryset is a 404).
* ``can(access, action, obj)``: the action table below, plus per-object rules (e.g. posted ledger entries
  are read-only, pastoral notes only for the assigned mentor).
* Form foreign keys are limited to what the user may see (``limit_choices``). Unknown related models get
  NO choices by default, so a new FK can never leak another department's records through a dropdown.
"""

from __future__ import annotations

import datetime as dt
from collections.abc import Iterable
from decimal import Decimal
from typing import Any, ClassVar

from django import forms
from django.core.exceptions import FieldDoesNotExist
from django.db import models
from django.db.models import Model, Q, QuerySet
from django.forms import modelform_factory
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone
from django.utils.text import capfirst

from .access import BRANCH, FOUNDER, HEAD, MEMBER, NONE, Access

REGISTRY: dict[tuple[str, str], Resource] = {}
BY_MODEL: dict[type[Model], Resource] = {}

# Related models that hold no personal data and may appear in any dropdown.
PUBLIC_FK_MODELS = {
    "branches.branch",
    "branches.country",
    "programs.program",
    "events.event",
    "portal.department",
    "leadership.department",
    "giving.givingcategory",
}

DEFAULT_PERMS = {"view": MEMBER, "add": MEMBER, "change": MEMBER, "delete": HEAD, "export": HEAD}


def register(cls: type[Resource]) -> type[Resource]:
    resource = cls()
    key = (resource.department, resource.slug)
    if key in REGISTRY:
        raise RuntimeError(f"Duplicate portal resource {key}")
    REGISTRY[key] = resource
    BY_MODEL.setdefault(resource.model, resource)
    return cls


def get_resource(department: str, slug: str) -> Resource | None:
    return REGISTRY.get((department, slug))


def resources_for(department: str) -> list[Resource]:
    return [r for (d, _), r in REGISTRY.items() if d == department]


class DateInput(forms.DateInput):
    input_type = "date"

    def __init__(self, **kw: Any) -> None:
        super().__init__(format="%Y-%m-%d", **kw)


class DateTimeInput(forms.DateTimeInput):
    input_type = "datetime-local"

    def __init__(self, **kw: Any) -> None:
        super().__init__(format="%Y-%m-%dT%H:%M", **kw)


class Resource:
    model: type[Model]
    department: str
    slug: str
    label: str = ""
    label_singular: str = ""
    icon: str = "list"
    nav: bool = True
    nav_group: str = ""
    description: str = ""

    list_fields: ClassVar[list[str]] = ["__str__"]
    filters: ClassVar[list[str]] = []
    search_fields: ClassVar[list[str]] = []  # plain (unencrypted) fields only
    fields: ClassVar[list[str] | None] = None  # form fields; None = no generic form
    form_class: type[forms.ModelForm] | None = None
    detail_fields: ClassVar[list[str] | None] = None
    export_fields: ClassVar[list[str] | None] = None
    children: ClassVar[list[tuple[str, str, str]]] = []  # (related accessor, child resource slug, title)
    parent_field: str | None = None  # FK to the parent shown on the parent's detail page
    ordering: ClassVar[list[str]] = []
    date_field: str | None = None  # for the date-range filter
    branch_lookup: str | None = None
    requester_field: str | None = None  # FK to portal.Department of the department that asked for it
    requester_actions: ClassVar[set[str]] = {"view", "add"}
    branch_actions: ClassVar[set[str]] = {"view"}
    perms: ClassVar[dict[str, int]] = {}
    sensitive: bool = False  # every list/detail view is audit-logged
    page_size: int = 25
    fk_querysets: ClassVar[dict[str, Any]] = {}

    def __init__(self) -> None:
        meta = self.model._meta
        self.label = self.label or capfirst(str(meta.verbose_name_plural))
        self.label_singular = self.label_singular or capfirst(str(meta.verbose_name))
        self.permissions = {**DEFAULT_PERMS, **self.perms}

    # ------------------------------------------------------------------ access
    def effective_level(self, access: Access) -> int:
        level = access.level(self.department)
        if level == BRANCH and self.branch_lookup is None:
            return NONE
        return level

    def requester_mode(self, access: Access) -> bool:
        return (
            bool(self.requester_field)
            and self.effective_level(access) < MEMBER
            and bool(access.member_departments())
        )

    def can(self, access: Access, action: str, obj: Model | None = None) -> bool:
        level = self.effective_level(access)
        if level == BRANCH:
            allowed = action in self.branch_actions
        elif level >= MEMBER:
            allowed = level >= self.permissions.get(action, FOUNDER + 1)
        elif self.requester_mode(access):
            allowed = action in self.requester_actions
        else:
            allowed = False
        if not allowed:
            return False
        if obj is not None:
            if not self.get_queryset(access).filter(pk=obj.pk).exists():
                return False
            return self.object_allows(access, action, obj)
        return True

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        """Per-object rules (override). Called only after the role check passed."""
        return True

    def get_queryset(self, access: Access) -> QuerySet:
        qs = self.model._default_manager.all()
        level = self.effective_level(access)
        if level >= BRANCH:
            qs = access.restrict_branch(qs, self.branch_lookup, self.department)
        elif self.requester_mode(access):
            # Requests filed by the user's own departments. A single-branch assignment only sees the
            # requests it filed itself (requests have no reliable branch of their own).
            wide = [c for c in access.member_departments() if not access.branch_restricted_in(c)]
            narrow = [c for c in access.member_departments() if access.branch_restricted_in(c)]
            qs = qs.filter(
                Q(**{f"{self.requester_field}__code__in": wide})
                | Q(**{f"{self.requester_field}__code__in": narrow, "requested_by": access.user})
            )
        else:
            return qs.none()
        qs = self.scope(access, qs)
        return qs.order_by(*self.ordering) if self.ordering else qs

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        """Extra row-level rules (override), e.g. hide minors from non-heads."""
        return qs

    def is_head(self, access: Access) -> bool:
        return self.effective_level(access) >= HEAD

    # ------------------------------------------------------------------ urls
    def url(self, name: str, obj: Model | None = None, **query: Any) -> str:
        args: list[Any] = [self.department, self.slug]
        if obj is not None:
            args.append(obj.pk)
        url = reverse(f"portal:resource_{name}", args=args)
        if query:
            from django.utils.http import urlencode

            url += "?" + urlencode(query)
        return url

    # ------------------------------------------------------------------ forms
    def get_form_class(self, access: Access, obj: Model | None = None) -> type[forms.ModelForm]:
        if self.form_class is not None:
            return self.form_class
        widgets: dict[str, Any] = {}
        for name in self.fields or []:
            field = self.model._meta.get_field(name)
            if isinstance(field, models.DateTimeField):
                widgets[name] = DateTimeInput()
            elif isinstance(field, models.DateField):
                widgets[name] = DateInput()
            elif isinstance(field, models.TextField) and not getattr(field, "plain_max_length", None):
                widgets[name] = forms.Textarea(attrs={"rows": 4})
        return modelform_factory(self.model, fields=self.fields, widgets=widgets)

    def initial(self, request: HttpRequest, access: Access) -> dict[str, Any]:
        initial: dict[str, Any] = {}
        if self.parent_field and request.GET.get("parent", "").isdigit():
            initial[self.parent_field] = int(request.GET["parent"])
        if self.requester_field and self.requester_mode(access):
            from .models import Department

            first = Department.objects.filter(code__in=access.member_departments()).first()
            if first:
                initial[self.requester_field] = first.pk
        for key in getattr(self, "initial_from_query", []):
            if request.GET.get(key, "").isdigit():
                initial[key] = int(request.GET[key])
        return initial

    def prepare_form(self, form: forms.ModelForm, access: Access) -> forms.ModelForm:
        for name, field in form.fields.items():
            if isinstance(field, forms.ModelChoiceField):
                field.queryset = self.limit_choices(access, name, field.queryset.model)
        return form

    def limit_choices(self, access: Access, field_name: str, related: type[Model]) -> QuerySet:
        custom = self.fk_querysets.get(field_name)
        if custom is not None:
            return custom(access)
        label = related._meta.label_lower
        if label == "accounts.user":
            return related._default_manager.filter(is_active=True, is_staff=True, deleted_at__isnull=True)
        if label == "branches.branch":
            return access.allowed_branches(self.department)
        if (
            label == "portal.department"
            and field_name == self.requester_field
            and self.requester_mode(access)
        ):
            return related._default_manager.filter(code__in=access.member_departments())
        if label == "events.event":
            return access.restrict_branch(related._default_manager.all(), "branch_id", self.department)
        if label in PUBLIC_FK_MODELS:
            return related._default_manager.all()
        resource = BY_MODEL.get(related)
        if resource is not None and resource.can(access, "view"):
            return resource.get_queryset(access)
        return related._default_manager.none()

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        """Fill bookkeeping fields. Override and call super() to add more."""
        user = request.user
        if created:
            for name in ("created_by", "recorded_by", "requested_by", "submitted_by", "entered_by", "author"):
                if hasattr(obj, f"{name}_id") and getattr(obj, f"{name}_id") is None:
                    setattr(obj, name, user)
        restricted, branch_id = access.branch_scope(self.department)
        if restricted and hasattr(obj, "branch_id") and not obj.branch_id:
            obj.branch_id = branch_id

    def after_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        """Side effects after a successful save (override)."""

    # ------------------------------------------------------------------ display
    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        """Workflow buttons on the detail page: dicts with label, url, style, confirm (override)."""
        return []

    def extra_context(self, request: HttpRequest, access: Access, obj: Model) -> dict[str, Any]:
        """Extra variables for a custom detail template (override)."""
        return {}

    def list_columns(self) -> list[tuple[str, str]]:
        return [(name, self.column_label(name)) for name in self.list_fields]

    def column_label(self, name: str) -> str:
        if name == "__str__":
            return self.label_singular
        attr = getattr(self, name, None)
        if callable(attr) and hasattr(attr, "short_description"):
            return attr.short_description  # type: ignore[no-any-return]
        try:
            return capfirst(str(self.model._meta.get_field(name).verbose_name))
        except FieldDoesNotExist:  # a property or method on the model
            return capfirst(name.replace("_", " "))

    def value(self, obj: Model, name: str) -> Any:
        """Plain display value (always rendered auto-escaped)."""
        if name == "__str__":
            return str(obj)
        own = getattr(self, name, None)
        if callable(own):
            return own(obj)
        display = getattr(obj, f"get_{name}_display", None)
        if callable(display):
            return display()
        value = getattr(obj, name, None)
        if isinstance(value, models.Manager):  # many-to-many: list the related records
            return ", ".join(str(item) for item in value.all()[:20]) or "—"
        if callable(value):
            value = value()
        return format_value(value)

    def detail_rows(self, obj: Model) -> list[tuple[str, Any, str]]:
        """(label, value, kind) where kind is 'text', 'long' or 'file'."""
        rows = []
        for name in self.detail_fields or self.fields or self.list_fields:
            kind = "text"
            try:
                field = self.model._meta.get_field(name)
                if isinstance(field, models.FileField):
                    kind = "file"
                elif isinstance(field, models.TextField) and not getattr(field, "plain_max_length", None):
                    kind = "long"
            except FieldDoesNotExist:
                kind = "text"  # computed value (property or resource method)
            rows.append((self.column_label(name), self.value(obj, name), kind if kind != "file" else name))
        return rows

    def filter_specs(self, access: Access) -> list[dict[str, Any]]:
        specs = []
        for name in self.filters:
            field = self.model._meta.get_field(name)
            if field.choices:
                options = [(str(k), v) for k, v in field.choices]
            elif isinstance(field, models.BooleanField):
                options = [("1", "Yes"), ("0", "No")]
            elif isinstance(field, models.ForeignKey):
                qs = self.limit_choices(access, name, field.related_model)
                options = [(str(o.pk), str(o)) for o in qs[:200]]
            else:
                continue
            specs.append({"name": name, "label": capfirst(str(field.verbose_name)), "options": options})
        return specs

    def apply_filters(self, qs: QuerySet, params: Any, access: Access) -> QuerySet:
        for spec in self.filter_specs(access):
            raw = params.get(spec["name"], "")
            if raw and raw in {k for k, _ in spec["options"]}:
                field = self.model._meta.get_field(spec["name"])
                value: Any = raw
                if isinstance(field, models.BooleanField):
                    value = raw == "1"
                qs = qs.filter(**{spec["name"]: value})
        term = (params.get("q") or "").strip()[:100]
        if term and self.search_fields:
            cond = models.Q()
            for name in self.search_fields:
                cond |= models.Q(**{f"{name}__icontains": term})
            qs = qs.filter(cond)
        if self.date_field:
            start, end = parse_date(params.get("from")), parse_date(params.get("to"))
            if start:
                qs = qs.filter(**{f"{self.date_field}__gte": start})
            if end:
                qs = qs.filter(**{f"{self.date_field}__lte": end})
        return qs


def parse_date(raw: str | None) -> dt.date | None:
    if not raw:
        return None
    try:
        return dt.date.fromisoformat(raw[:10])
    except ValueError:
        return None


def format_value(value: Any) -> Any:
    if value is None or value == "":
        return "—"
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, dt.datetime):
        return timezone.localtime(value).strftime("%d %b %Y %H:%M") if timezone.is_aware(value) else value
    if isinstance(value, dt.date):
        return value.strftime("%d %b %Y")
    if isinstance(value, Decimal):
        return f"{value:,.2f}"
    if isinstance(value, list | tuple):
        return ", ".join(str(v) for v in value) or "—"
    if isinstance(value, models.fields.files.FieldFile):
        return "Attached" if value else "—"
    return value


def choice_labels(choices: Iterable[tuple[str, str]], values: Iterable[str]) -> str:
    mapping = dict(choices)
    return ", ".join(str(mapping.get(v, v)) for v in values) or "—"
