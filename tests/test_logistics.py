"""Logistics & Procurement: full procurement chain, 3 quotations, Finance budget, approval segregation."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.conf import settings
from django.utils import timezone

from accounts.roles import FINANCE, LOGISTICS, MEDIA, MEMBERSHIP
from audit.models import AuditLog
from finance.models import BudgetLine
from logistics.models import AssetLoan, InventoryItem, PurchaseOrder, PurchaseRequest, Quotation, Supplier
from portal.models import Department

pytestmark = pytest.mark.django_db
P = "/" + settings.PORTAL_URL


def dept(code: str) -> Department:
    return Department.objects.get(code=code)


@pytest.fixture
def people(make_staff, verified_client):  # type: ignore[no-untyped-def]
    media_user = make_staff(MEDIA, email="media@example.test")
    return {
        "media_user": media_user,
        "media": verified_client(media_user),
        "clerk": verified_client(make_staff(LOGISTICS, email="clerk@example.test")),
        "head": verified_client(make_staff(LOGISTICS, email="lhead@example.test", heads={"logistics"})),
        "finance": verified_client(make_staff(FINANCE, email="fin@example.test")),
        "membership": verified_client(make_staff(MEMBERSHIP, email="mem@example.test")),
    }


def _quotes(pr: PurchaseRequest, amounts=(300, 250, 400)) -> list[Quotation]:  # type: ignore[no-untyped-def]
    out = []
    for i, amount in enumerate(amounts):
        supplier = Supplier.objects.create(name=f"Supplier {i}", rating=3 + i % 2)
        out.append(
            Quotation.objects.create(request=pr, supplier=supplier, amount=Decimal(amount), delivery_days=5)
        )
    return out


def test_full_procurement_chain(people) -> None:  # type: ignore[no-untyped-def]
    media, clerk, head, finance = people["media"], people["clerk"], people["head"], people["finance"]
    # 1. Media (another department) asks for a purchase for itself
    resp = media.post(
        P + "logistics/requests/new/",
        {
            "title": "Banner printing",
            "requesting_department": dept("media").pk,
            "description": "3 roll-up banners",
            "estimated_cost": "300",
            "currency": "USD",
        },
    )
    assert resp.status_code == 302
    pr = PurchaseRequest.objects.get()
    assert pr.requested_by == people["media_user"] and pr.status == "draft"
    media.post(P + f"logistics/requests/{pr.pk}/step/submit/")
    pr.refresh_from_db()
    assert pr.status == "submitted" and pr.number.startswith("PR-")
    # 2. fewer than 3 quotations: no recommendation
    q1, q2, q3 = _quotes(pr)
    Quotation.objects.filter(pk=q3.pk).delete()
    clerk.post(P + f"logistics/requests/{pr.pk}/recommend/", {"quotation": q2.pk})
    pr.refresh_from_db()
    assert pr.status == "submitted"
    q3 = Quotation.objects.create(
        request=pr, supplier=Supplier.objects.create(name="Third"), amount=Decimal("400")
    )
    # not the cheapest without a reason -> refused
    clerk.post(P + f"logistics/requests/{pr.pk}/recommend/", {"quotation": q1.pk})
    pr.refresh_from_db()
    assert pr.status == "submitted"
    page = clerk.get(P + f"logistics/requests/{pr.pk}/").content.decode()
    assert "Quotation comparison" in page and "Cheapest" in page
    clerk.post(P + f"logistics/requests/{pr.pk}/recommend/", {"quotation": q2.pk})
    pr.refresh_from_db()
    assert pr.status == "recommended" and pr.recommended_quotation == q2
    # 3. approval impossible before Finance confirms the budget
    head.post(P + f"logistics/requests/{pr.pk}/step/approve/")
    pr.refresh_from_db()
    assert pr.status == "recommended"
    # Finance: budget line of ANOTHER department is refused
    other_line = BudgetLine.objects.create(
        year=timezone.localdate().year, department=dept("missions"), category="media", name="x", amount=1000
    )
    line = BudgetLine.objects.create(
        year=timezone.localdate().year,
        department=dept("media"),
        category="media",
        name="Printing",
        amount=1000,
    )
    finance.post(P + f"finance/procurement/{pr.pk}/confirm-budget/", {"budget_line": other_line.pk})
    pr.refresh_from_db()
    assert pr.status == "recommended"
    finance.post(P + f"finance/procurement/{pr.pk}/confirm-budget/", {"budget_line": line.pk})
    pr.refresh_from_db()
    assert pr.status == "budget_confirmed" and pr.budget_line == line
    # 4. clerk cannot approve; head can
    assert clerk.post(P + f"logistics/requests/{pr.pk}/step/approve/").status_code == 403
    head.post(P + f"logistics/requests/{pr.pk}/step/approve/")
    pr.refresh_from_db()
    assert pr.status == "approved"
    # 5. PO, delivery, inventory, close
    clerk.post(P + f"logistics/requests/{pr.pk}/step/order/")
    order = PurchaseOrder.objects.get(request=pr)
    assert order.amount == Decimal("250") and order.number.startswith("PO-")
    clerk.post(
        P + "logistics/deliveries/new/",
        {"order": order.pk, "delivered_on": timezone.localdate().isoformat(), "is_complete": "on"},
    )
    pr.refresh_from_db()
    assert pr.status == "received"
    clerk.post(
        P + f"logistics/orders/{order.pk}/receive/",
        {"name": "Roll-up banner", "quantity": 3, "kind": "asset"},
    )
    assert InventoryItem.objects.get(purchase_order=order).quantity == 3
    clerk.post(P + f"logistics/requests/{pr.pk}/step/close/")
    pr.refresh_from_db()
    assert pr.status == "closed"
    assert AuditLog.objects.filter(action=AuditLog.Action.APPROVE, object_id=str(pr.pk)).count() == 2


def test_requester_cannot_approve_own_request_even_as_head(make_staff, verified_client) -> None:  # type: ignore[no-untyped-def]
    head_user = make_staff(LOGISTICS, heads={"logistics"})
    pr = PurchaseRequest.objects.create(
        title="Chairs",
        requesting_department=dept("logistics"),
        description="x",
        status="budget_confirmed",
        requested_by=head_user,
    )
    verified_client(head_user).post(P + f"logistics/requests/{pr.pk}/step/approve/")
    pr.refresh_from_db()
    assert pr.status == "budget_confirmed"


def test_requesting_department_sees_only_its_own_requests(people) -> None:  # type: ignore[no-untyped-def]
    mine = PurchaseRequest.objects.create(
        title="Media cameras", requesting_department=dept("media"), description="x"
    )
    theirs = PurchaseRequest.objects.create(
        title="Membership forms", requesting_department=dept("membership"), description="x"
    )
    media = people["media"]
    listing = media.get(P + "logistics/requests/").content.decode()
    assert "Media cameras" in listing and "Membership forms" not in listing
    assert media.get(P + f"logistics/requests/{theirs.pk}/").status_code == 404
    assert media.get(P + f"logistics/requests/{mine.pk}/").status_code == 200
    # cannot file a request in another department's name
    media.post(
        P + "logistics/requests/new/",
        {
            "title": "Sneaky",
            "requesting_department": dept("finance").pk,
            "description": "x",
            "currency": "USD",
        },
    )
    assert not PurchaseRequest.objects.filter(title="Sneaky").exists()
    # cannot see the rest of Logistics
    assert media.get(P + "logistics/").status_code == 403
    assert media.get(P + "logistics/inventory/").status_code == 403
    assert media.get(P + "logistics/suppliers/").status_code == 403
    assert media.post(P + f"logistics/requests/{mine.pk}/step/order/").status_code == 403


def test_finance_queue_and_logistics_isolation(people) -> None:  # type: ignore[no-untyped-def]
    pr = PurchaseRequest.objects.create(
        title="Generator", requesting_department=dept("logistics"), description="x", status="recommended"
    )
    assert people["finance"].get(P + f"finance/procurement/{pr.pk}/").status_code == 200
    assert people["clerk"].get(P + f"finance/procurement/{pr.pk}/confirm-budget/").status_code == 403
    assert people["membership"].get(P + f"finance/procurement/{pr.pk}/").status_code == 403


def test_inventory_alerts_and_loans(people) -> None:  # type: ignore[no-untyped-def]
    paper = InventoryItem.objects.create(name="A4 paper", kind="consumable", quantity=2, reorder_level=5)
    mixer = InventoryItem.objects.create(
        name="Sound mixer",
        quantity=1,
        maintenance_interval_days=30,
        last_maintenance=timezone.localdate() - timedelta(days=40),
    )
    AssetLoan.objects.create(
        item=mixer, borrower="Youth team", due_back=timezone.localdate() - timedelta(days=1)
    )
    assert mixer.available == 0 and paper.is_low
    page = people["head"].get(P + "logistics/")
    kpis = {k.code: k.value for k in page.context["board"].kpis}
    assert kpis["low_stock"] == 1 and kpis["maintenance_due"] == 1
    texts = " ".join(i.text for i in page.context["board"].attention)
    assert "A4 paper" in texts and "Not returned" in texts


def test_quotations_only_while_collecting(people) -> None:  # type: ignore[no-untyped-def]
    pr = PurchaseRequest.objects.create(
        title="Tents", requesting_department=dept("missions"), description="x", status="approved"
    )
    supplier = Supplier.objects.create(name="Tents Ltd")
    people["clerk"].post(
        P + "logistics/quotations/new/", {"request": pr.pk, "supplier": supplier.pk, "amount": "10"}
    )
    assert not Quotation.objects.exists()
