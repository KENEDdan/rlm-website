"""Logistics & Procurement in the staff portal (+ Finance's budget-confirmation queue)."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Any, ClassVar

from django.db.models import Count, Model, QuerySet, Sum
from django.http import HttpRequest
from django.urls import reverse
from django.utils import timezone

from portal.access import FOUNDER, HEAD, MEMBER, Access
from portal.charts import Chart, grouped_counts, monthly_series
from portal.dashboards import (
    KPI,
    Action,
    Dashboard,
    Filters,
    Item,
    dashboard,
    executive_summary,
    handoffs,
    pending_approvals,
)
from portal.resources import Resource, register

from .models import (
    AssetLoan,
    DeliveryNote,
    InventoryItem,
    LogisticsPlan,
    LogisticsTask,
    MaintenanceRecord,
    PurchaseOrder,
    PurchaseRequest,
    Quotation,
    Supplier,
)
from .services import delivery_recorded

DEPT = "logistics"
S = PurchaseRequest.Status


def _step(
    pk: int, step: str, label: str, style: str = "", method: str = "post", confirm: str = ""
) -> dict[str, Any]:
    return {
        "label": label,
        "url": reverse("portal:logistics:request_step", args=[pk, step]),
        "style": style,
        "method": method,
        "confirm": confirm,
    }


class _Logistics(Resource):
    department = DEPT


@register
class RequestResource(_Logistics):
    model = PurchaseRequest
    slug = "requests"
    label = "Purchase requests"
    nav_group = "Procurement"
    description = (
        "Any department can ask for a purchase here; Logistics collects quotations and follows it through."
    )
    list_fields: ClassVar = [
        "number",
        "title",
        "requesting_department",
        "status",
        "needed_by",
        "estimated_cost",
    ]
    filters: ClassVar = ["status", "requesting_department", "branch"]
    search_fields: ClassVar = ["number", "title"]
    fields: ClassVar = [
        "title",
        "requesting_department",
        "branch",
        "event",
        "description",
        "needed_by",
        "estimated_cost",
        "currency",
    ]
    detail_fields: ClassVar = [
        "number",
        "status",
        *fields,
        "requested_by",
        "recommendation_note",
        "budget_line",
        "budget_confirmed_by",
        "approved_by",
        "approved_at",
        "rejection_note",
    ]
    children: ClassVar = [("quotations", "quotations", "Quotations")]
    detail_template = "logistics/request_detail.html"
    date_field = "created_at"
    requester_field = "requesting_department"
    requester_actions: ClassVar = {"view", "add", "change"}
    perms: ClassVar = {"delete": HEAD, "export": HEAD}

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        pr: PurchaseRequest = obj  # type: ignore[assignment]
        if action == "change":
            if self.requester_mode(access):
                return pr.status == S.DRAFT and pr.requested_by_id == access.user.pk
            return pr.is_editable
        if action == "delete":
            return pr.status == S.DRAFT
        return True

    def extra_context(self, request: HttpRequest, access: Access, obj: Model) -> dict[str, Any]:
        from .services import comparison

        return {
            "comparison": comparison(obj),  # type: ignore[arg-type]
            "can_recommend": self.effective_level(access) >= MEMBER,
        }

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        pr: PurchaseRequest = obj  # type: ignore[assignment]
        logistics = self.effective_level(access) >= MEMBER
        out = []
        if pr.status == S.DRAFT and (logistics or pr.requested_by_id == access.user.pk):
            out.append(_step(pr.pk, "submit", "Submit request", "primary"))
        if pr.status == S.BUDGET_CONFIRMED and access.is_head(DEPT) and pr.requested_by_id != access.user.pk:
            out.append(_step(pr.pk, "approve", "Approve purchase", "primary"))
        if (
            logistics
            and pr.status in (S.SUBMITTED, S.RECOMMENDED, S.BUDGET_CONFIRMED)
            and access.is_head(DEPT)
        ):
            out.append(_step(pr.pk, "reject", "Reject", method="get"))
        if logistics and pr.status == S.APPROVED:
            out.append(_step(pr.pk, "order", "Issue purchase order", "primary"))
        if logistics and pr.status == S.RECEIVED:
            out.append(_step(pr.pk, "close", "Close request"))
        return out


@register
class QuotationResource(_Logistics):
    model = Quotation
    slug = "quotations"
    nav = False
    parent_field = "request"
    list_fields: ClassVar = ["supplier", "amount", "delivery_days", "valid_until"]
    fields: ClassVar = ["request", "supplier", "amount", "delivery_days", "valid_until", "file", "notes"]
    fk_querysets: ClassVar = {
        "request": lambda access: PurchaseRequest.objects.filter(status=S.SUBMITTED),
        "supplier": lambda access: Supplier.objects.filter(is_active=True),
    }

    def object_allows(self, access: Access, action: str, obj: Model) -> bool:
        if action in ("change", "delete"):
            return obj.request.status == S.SUBMITTED  # type: ignore[attr-defined]
        return True


@register
class OrderResource(_Logistics):
    model = PurchaseOrder
    slug = "orders"
    label = "Purchase orders"
    nav_group = "Procurement"
    list_fields: ClassVar = ["number", "supplier", "amount", "issued_on", "expected_delivery", "late"]
    filters: ClassVar = ["supplier"]
    search_fields: ClassVar = ["number"]
    detail_fields: ClassVar = [
        "number",
        "request",
        "supplier",
        "amount",
        "issued_on",
        "issued_by",
        "expected_delivery",
    ]
    children: ClassVar = [("deliveries", "deliveries", "Delivery notes")]
    date_field = "issued_on"
    perms: ClassVar = {"add": FOUNDER + 1, "change": FOUNDER + 1, "delete": FOUNDER + 1}

    def late(self, obj: PurchaseOrder) -> str:
        return "Late" if obj.is_late else ""

    late.short_description = "Delivery"  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        out = [
            {
                "label": "Record a delivery",
                "url": DeliveryResource().url("create", parent=obj.pk),
                "method": "get",
                "style": "primary",
            }
        ]
        if obj.request.status in (S.RECEIVED, S.CLOSED):  # type: ignore[attr-defined]
            out.append(
                {
                    "label": "Add to inventory",
                    "url": reverse("portal:logistics:receive", args=[obj.pk]),
                    "method": "get",
                }
            )
        return out


@register
class DeliveryResource(_Logistics):
    model = DeliveryNote
    slug = "deliveries"
    nav = False
    parent_field = "order"
    list_fields: ClassVar = ["delivered_on", "note_number", "is_complete", "received_by"]
    fields: ClassVar = ["order", "delivered_on", "note_number", "is_complete", "condition_notes", "file"]
    perms: ClassVar = {"change": HEAD, "delete": FOUNDER + 1}

    def before_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        super().before_save(request, access, obj, created)
        if created:
            obj.received_by = request.user  # type: ignore[attr-defined]

    def after_save(self, request: HttpRequest, access: Access, obj: Model, created: bool) -> None:
        delivery_recorded(obj)  # type: ignore[arg-type]


@register
class SupplierResource(_Logistics):
    model = Supplier
    slug = "suppliers"
    label = "Supplier register"
    nav_group = "Procurement"
    list_fields: ClassVar = ["name", "category", "rating", "is_active", "orders_count"]
    filters: ClassVar = ["is_active", "rating"]
    search_fields: ClassVar = ["name", "category"]
    fields: ClassVar = [
        "name",
        "category",
        "contact_person",
        "phone",
        "email",
        "address",
        "rating",
        "is_active",
        "notes",
    ]
    perms: ClassVar = {"delete": FOUNDER + 1}

    def orders_count(self, obj: Supplier) -> int:
        return obj.orders.count()

    orders_count.short_description = "Orders"  # type: ignore[attr-defined]


@register
class InventoryResource(_Logistics):
    model = InventoryItem
    slug = "inventory"
    label = "Assets & inventory"
    nav_group = "Assets"
    list_fields: ClassVar = [
        "name",
        "kind",
        "quantity",
        "unit",
        "available_qty",
        "condition",
        "location",
        "next_due",
    ]
    filters: ClassVar = ["kind", "condition", "branch", "custodian"]
    search_fields: ClassVar = ["name", "tag", "category", "location"]
    fields: ClassVar = [
        "name",
        "kind",
        "category",
        "tag",
        "quantity",
        "unit",
        "reorder_level",
        "condition",
        "location",
        "branch",
        "custodian",
        "maintenance_interval_days",
        "last_maintenance",
        "notes",
    ]
    children: ClassVar = [
        ("loans", "check-outs", "Check-out history"),
        ("maintenance", "maintenance", "Maintenance"),
    ]
    perms: ClassVar = {"delete": HEAD}

    def available_qty(self, obj: InventoryItem) -> int:
        return obj.available

    available_qty.short_description = "Available"  # type: ignore[attr-defined]

    def next_due(self, obj: InventoryItem) -> Any:
        due = obj.next_maintenance
        return due.strftime("%d %b %Y") if due else "—"

    next_due.short_description = "Next maintenance"  # type: ignore[attr-defined]


@register
class LoanResource(_Logistics):
    model = AssetLoan
    slug = "check-outs"
    label = "Check-in / check-out"
    nav_group = "Assets"
    parent_field = "item"
    list_fields: ClassVar = ["item", "borrower", "quantity", "out_on", "due_back", "returned_on"]
    filters: ClassVar = ["department"]
    fields: ClassVar = [
        "item",
        "borrower",
        "department",
        "quantity",
        "out_on",
        "due_back",
        "returned_on",
        "return_condition",
        "notes",
    ]
    date_field = "out_on"


@register
class MaintenanceResource(_Logistics):
    model = MaintenanceRecord
    slug = "maintenance"
    nav = False
    parent_field = "item"
    list_fields: ClassVar = ["date", "item", "description", "cost"]
    fields: ClassVar = ["item", "date", "description", "cost", "done_by"]


@register
class PlanResource(_Logistics):
    model = LogisticsPlan
    slug = "event-logistics"
    label = "Event logistics plans"
    nav_group = "Events"
    description = (
        "Transport, accommodation, feeding and equipment checklists per conference, crusade or outreach."
    )
    list_fields: ClassVar = ["title", "kind", "start_date", "location", "status", "progress_pct"]
    filters: ClassVar = ["kind", "status", "branch"]
    fields: ClassVar = [
        "title",
        "kind",
        "event",
        "start_date",
        "end_date",
        "location",
        "branch",
        "expected_attendance",
        "coordinator",
        "status",
    ]
    children: ClassVar = [("tasks", "plan-tasks", "Checklist")]
    date_field = "start_date"
    ordering: ClassVar = ["start_date"]

    def progress_pct(self, obj: LogisticsPlan) -> str:
        return f"{obj.progress}%"

    progress_pct.short_description = "Checklist done"  # type: ignore[attr-defined]


@register
class TaskResource(_Logistics):
    model = LogisticsTask
    slug = "plan-tasks"
    nav = False
    parent_field = "plan"
    list_fields: ClassVar = ["category", "description", "quantity", "responsible", "due", "done"]
    fields: ClassVar = [
        "plan",
        "category",
        "description",
        "quantity",
        "estimated_cost",
        "responsible",
        "due",
        "done",
    ]


# ------------------------------------------------------------------------------------------ Finance's queue
@register
class ProcurementBudgetResource(Resource):
    """Finance sees purchase requests to confirm the budget (the cross-department handoff)."""

    model = PurchaseRequest
    department = "finance"
    slug = "procurement"
    label = "Purchases: budget confirmation"
    nav_group = "Accounts"
    list_fields: ClassVar = ["number", "title", "requesting_department", "status", "recommended_amount"]
    filters: ClassVar = ["status", "requesting_department"]
    detail_fields: ClassVar = [
        "number",
        "title",
        "requesting_department",
        "description",
        "status",
        "recommended_amount",
        "recommendation_note",
        "budget_line",
    ]
    perms: ClassVar = {"add": FOUNDER + 1, "change": FOUNDER + 1, "delete": FOUNDER + 1, "export": HEAD}

    def scope(self, access: Access, qs: QuerySet) -> QuerySet:
        return qs.exclude(status__in=[S.DRAFT, S.SUBMITTED])

    def recommended_amount(self, obj: PurchaseRequest) -> str:
        q = obj.recommended_quotation
        return f"{q.amount:,.2f} ({q.supplier})" if q else "—"

    recommended_amount.short_description = "Recommended quotation"  # type: ignore[attr-defined]

    def actions(self, request: HttpRequest, access: Access, obj: Model) -> list[dict[str, Any]]:
        if obj.status == S.RECOMMENDED:  # type: ignore[attr-defined]
            return [
                {
                    "label": "Confirm budget",
                    "url": reverse("portal:logistics:confirm_budget", args=[obj.pk]),
                    "method": "get",
                    "style": "primary",
                }
            ]
        return []


# ------------------------------------------------------------------------------------------ dashboard
@dashboard(DEPT)
def build(request: HttpRequest, access: Access, filters: Filters) -> Dashboard:
    requests = RequestResource().get_queryset(access)
    if filters.branch_id:
        requests = requests.filter(branch_id=filters.branch_id)
    open_requests = requests.filter(status__in=PurchaseRequest.OPEN)
    awaiting_finance = requests.filter(status=S.RECOMMENDED)
    awaiting_approval = requests.filter(status=S.BUDGET_CONFIRMED)
    orders = PurchaseOrder.objects.filter(request__in=requests)
    period_orders = orders.filter(issued_on__gte=filters.start, issued_on__lte=filters.end)
    spend = period_orders.aggregate(t=Sum("amount"))["t"] or Decimal("0")
    linked_budget = (
        PurchaseRequest.objects.filter(order__in=period_orders, budget_line__isnull=False)
        .values("budget_line")
        .distinct()
        .aggregate(t=Sum("budget_line__amount"))["t"]
    ) or Decimal("0")
    late = [
        o
        for o in orders.filter(expected_delivery__lt=timezone.localdate()).select_related("supplier")
        if o.is_late
    ]
    items = InventoryItem.objects.all()
    if filters.branch_id:
        items = items.filter(branch_id=filters.branch_id)
    low = [i for i in items.filter(kind=InventoryItem.Kind.CONSUMABLE) if i.is_low]
    soon = timezone.localdate() + timedelta(days=14)
    due_maintenance = [
        i
        for i in items.filter(maintenance_interval_days__isnull=False)
        if i.next_maintenance and i.next_maintenance <= soon
    ]
    url = RequestResource().url("list")
    kpis = [
        KPI("Open requests", open_requests.count(), url=url, code="open_requests"),
        KPI(
            "Awaiting Finance",
            awaiting_finance.count(),
            url=f"{url}?status=recommended",
            code="awaiting_finance",
        ),
        KPI(
            "Awaiting approval",
            awaiting_approval.count(),
            url=f"{url}?status=budget_confirmed",
            code="pending_approvals",
            status="warn" if awaiting_approval.exists() else "",
        ),
        KPI(
            "Spend (period)",
            f"{spend:,.2f}",
            f"Orders issued · {int(spend * 100 / linked_budget) if linked_budget else 0}% of their budget lines",
            OrderResource().url("list"),
            code="spend",
        ),
        KPI("Late deliveries", len(late), code="late_deliveries", status="bad" if late else ""),
        KPI(
            "Low stock",
            len(low),
            url=InventoryResource().url("list") + "?kind=consumable",
            code="low_stock",
            status="warn" if low else "",
        ),
        KPI("Maintenance due (14 days)", len(due_maintenance), code="maintenance_due"),
    ]
    status_labels = dict(S.choices)
    charts = [
        Chart(
            "Purchase order spend per month",
            "bar",
            monthly_series(orders, "issued_on", filters.start, filters.end, sum_field="amount"),
        ),
        Chart("Open requests by status", "hbar", grouped_counts(open_requests, "status", status_labels)),
        Chart(
            "Requests by department (period)",
            "hbar",
            grouped_counts(
                requests.filter(created_at__date__gte=filters.start, created_at__date__lte=filters.end),
                "requesting_department__name",
            ),
        ),
    ]
    attention = [
        Item(f"Late: {o}", f"Expected {o.expected_delivery:%d %b}", OrderResource().url("detail", o), "bad")
        for o in late[:5]
    ]
    attention += [
        Item(
            f"Low stock: {i.name} ({i.quantity} {i.unit})",
            i.location,
            InventoryResource().url("detail", i),
            "warn",
        )
        for i in low[:5]
    ]
    attention += [
        Item(
            f"Maintenance due: {i}",
            f"{i.next_maintenance:%d %b}",
            InventoryResource().url("detail", i),
            "warn",
        )
        for i in due_maintenance[:5]
    ]
    overdue_loans = list(
        AssetLoan.objects.filter(returned_on__isnull=True, due_back__lt=timezone.localdate())[:5]
    )
    attention += [
        Item(
            f"Not returned: {loan}", f"Due {loan.due_back:%d %b}", LoanResource().url("detail", loan), "warn"
        )
        for loan in overdue_loans
    ]
    quotes_needed = requests.filter(status=S.SUBMITTED).annotate(n=Count("quotations")).filter(n__lt=3)
    attention += [
        Item(f"Needs quotations ({r.n}/3): {r}", "", RequestResource().url("detail", r), "")
        for r in quotes_needed[:5]
    ]
    activity = [
        Item(str(r), r.get_status_display(), RequestResource().url("detail", r))
        for r in requests.order_by("-updated_at")[:6]
    ]
    upcoming = LogisticsPlan.objects.filter(start_date__gte=timezone.localdate()).order_by("start_date")[:6]
    sections = [
        {
            "title": "Upcoming event logistics",
            "columns": ["Event", "Starts", "Location", "Checklist done"],
            "rows": [
                [p.title, p.start_date.strftime("%d %b %Y"), p.location or "—", f"{p.progress}%"]
                for p in upcoming
            ],
            "empty": "No upcoming plans.",
        }
    ]
    actions = [
        Action("New purchase request", RequestResource().url("create"), primary=True),
        Action("Add inventory item", InventoryResource().url("create")),
        Action("Plan event logistics", PlanResource().url("create")),
    ]
    return Dashboard(
        title="Logistics & Procurement",
        kpis=kpis,
        charts=charts,
        attention=attention,
        activity=activity,
        actions=actions,
        sections=sections,
    )


@executive_summary(DEPT)
def summary(filters: Filters) -> list[KPI]:
    open_requests = PurchaseRequest.objects.filter(status__in=PurchaseRequest.OPEN)
    late = sum(
        1 for o in PurchaseOrder.objects.filter(expected_delivery__lt=timezone.localdate()) if o.is_late
    )
    low = sum(1 for i in InventoryItem.objects.filter(kind=InventoryItem.Kind.CONSUMABLE) if i.is_low)
    return [
        KPI("Open requests", open_requests.count()),
        KPI("Awaiting approval", open_requests.filter(status=S.BUDGET_CONFIRMED).count()),
        KPI("Late deliveries", late, status="bad" if late else ""),
        KPI("Low stock items", low),
    ]


@pending_approvals(DEPT)
def pending() -> list[Item]:
    count = PurchaseRequest.objects.filter(status=S.BUDGET_CONFIRMED).count()
    if not count:
        return []
    return [
        Item(
            f"{count} purchase request(s) awaiting approval",
            "Logistics",
            RequestResource().url("list") + "?status=budget_confirmed",
            "warn",
        )
    ]


@handoffs
def procurement_handoffs() -> list[Item]:
    count = PurchaseRequest.objects.filter(status=S.RECOMMENDED).count()
    if not count:
        return []
    return [
        Item(
            f"Logistics → Finance: {count} purchase(s) waiting for budget confirmation",
            "",
            ProcurementBudgetResource().url("list") + "?status=recommended",
            "warn",
        )
    ]
