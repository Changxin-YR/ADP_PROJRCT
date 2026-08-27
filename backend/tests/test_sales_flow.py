from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app import create_app
from backend.config.settings import Settings
from backend.layers.common.governance.lifecycle import DomainError
from backend.layers.features.sales.sales_service import SalesService
from fake_auth_store import FakeAuthStore


ROOT = Path(__file__).parents[2]


def actor(user_id: int, *permissions: str) -> dict[str, Any]:
    return {"id": user_id, "permissions": list(permissions), "data_scopes": [{"scope_type": "farm"}]}


def order_payload(**overrides: Any) -> dict[str, Any]:
    return {
        "code": "SO-1", "name": "一号塘鲈鱼销售", "customer_id": 4, "pond_id": 2,
        "batch_id": 3, "species": "鲈鱼", "quantity": 100, "unit": "kg",
        "unit_price": 26, "sold_at": "2026-08-17", "due_date": "2026-09-17", **overrides,
    }


class SalesStore:
    def __init__(self) -> None:
        self.orders: dict[int, dict[str, Any]] = {}
        self.deliveries: dict[int, dict[str, Any]] = {}
        self.receipts: dict[int, dict[str, Any]] = {}
        self.receipt_handlers: dict[int, set[int]] = {}
        self.receivables = [{"id": 31, "status": "unpaid", "balance": 1000, "amount": 1000}]

    @staticmethod
    def page(items: list[dict[str, Any]]) -> dict[str, Any]:
        return {"items": items, "page": 1, "page_size": 20, "total": len(items), "has_next": False}

    def list_orders(self, **_: Any) -> dict[str, Any]: return self.page(list(self.orders.values()))
    def get_order(self, record_id: int, **_: Any) -> dict[str, Any] | None: return self.orders.get(record_id)

    def create_order(self, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = {**payload, "id": len(self.orders) + 1, "status": "draft", "row_version": 1, "created_by": user_id, "delivered_quantity": 0}
        self.orders[row["id"]] = row; return row

    def update_order(self, record_id: int, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.orders[record_id]; row.update(payload, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def set_order_status(self, record_id: int, status: str, *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.orders[record_id]; row.update(status=status, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def cancel_order(self, record_id: int, *, user_id: int, reason: str, **_: Any) -> dict[str, Any]:
        row = self.orders[record_id]; row.update(status="cancelled", cancellation_reason=reason, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def delete_order_draft(self, record_id: int, **_: Any) -> dict[str, Any]: return self.orders.pop(record_id)
    def list_deliveries(self, **_: Any) -> dict[str, Any]: return self.page(list(self.deliveries.values()))
    def get_delivery(self, record_id: int, **_: Any) -> dict[str, Any] | None: return self.deliveries.get(record_id)

    def create_delivery(self, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = {**payload, "id": len(self.deliveries) + 1, "status": "draft", "row_version": 1, "created_by": user_id}
        self.deliveries[row["id"]] = row; return row

    def update_delivery(self, record_id: int, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.deliveries[record_id]; row.update(payload, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def set_delivery_status(self, record_id: int, status: str, *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.deliveries[record_id]; row.update(status=status, row_version=row["row_version"] + 1, updated_by=user_id)
        if status == "verified":
            order = self.orders[row["sales_order_id"]]; order["delivered_quantity"] += row["quantity"]
            order["status"] = "fully_delivered" if order["delivered_quantity"] == order["quantity"] else "partially_delivered"
        return row

    def create_delivery_correction(self, record_id: int, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        return self.create_delivery({**self.deliveries[record_id], **payload, "correction_of_id": record_id}, user_id=user_id)

    def delete_delivery_draft(self, record_id: int, **_: Any) -> dict[str, Any]: return self.deliveries.pop(record_id)
    def list_receivables(self, **_: Any) -> dict[str, Any]: return self.page(self.receivables)
    def list_receipts(self, **_: Any) -> dict[str, Any]: return self.page(list(self.receipts.values()))
    def get_receipt(self, record_id: int, **_: Any) -> dict[str, Any] | None: return self.receipts.get(record_id)

    def create_receipt(self, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = {**payload, "id": len(self.receipts) + 1, "status": "draft", "row_version": 1, "created_by": user_id}
        self.receipts[row["id"]] = row; self.receipt_handlers[row["id"]] = {user_id}; return row

    def update_receipt(self, record_id: int, payload: dict[str, Any], *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.receipts[record_id]; self.receipt_handlers[record_id].add(user_id); row.update(payload, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def set_receipt_status(self, record_id: int, status: str, *, user_id: int, **_: Any) -> dict[str, Any]:
        row = self.receipts[record_id]
        if status == "submitted": self.receipt_handlers[record_id].add(user_id)
        row.update(status=status, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def receipt_was_handled_by(self, record_id: int, user_id: int) -> bool: return user_id in self.receipt_handlers[record_id]

    def cancel_receipt(self, record_id: int, *, user_id: int, reason: str, **_: Any) -> dict[str, Any]:
        row = self.receipts[record_id]; row.update(status="cancelled", cancellation_reason=reason, row_version=row["row_version"] + 1, updated_by=user_id); return row

    def reverse_receipt(self, record_id: int, **_: Any) -> dict[str, Any]: self.receipts[record_id]["reversal_id"] = 9; return {"id": 9}
    def delete_receipt_draft(self, record_id: int, **_: Any) -> dict[str, Any]: return self.receipts.pop(record_id)


def test_submitted_sales_edit_bumps_version_and_approved_is_read_only() -> None:
    service = SalesService(SalesStore()); maker = actor(7, "sales.view", "sales.manage"); checker = actor(8, "sales.verify", "sales.manage")
    order = service.create_order(maker, order_payload())
    order = service.submit_order(maker, order["id"], {"expected_version": 1})
    order = service.update_order(maker, order["id"], {"expected_version": 2, "quantity": 120})
    with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
        service.approve_order(actor(7, "sales.verify"), order["id"], {"expected_version": 3})
    order = service.approve_order(checker, order["id"], {"expected_version": 3})
    assert order["allowed_actions"] == ["view", "deliver"]
    with pytest.raises(DomainError, match="RECORD_READ_ONLY"):
        service.update_order(maker, order["id"], {"expected_version": 4, "quantity": 130})


def test_sales_due_date_cannot_precede_sale_date() -> None:
    service = SalesService(SalesStore())
    with pytest.raises(DomainError, match="SALES_DATE_INVALID"):
        service.create_order(actor(7, "sales.manage"), order_payload(sold_at="2026-09-10", due_date="2026-09-01"))


def test_partial_and_full_delivery_are_verified_separately() -> None:
    store = SalesStore(); service = SalesService(store)
    maker = actor(7, "sales.view", "sales.manage"); checker = actor(8, "sales.verify")
    order = service.create_order(maker, order_payload()); order = service.submit_order(maker, order["id"], {"expected_version": 1})
    service.approve_order(checker, order["id"], {"expected_version": 2})
    first = service.create_delivery(maker, {"code": "SD-1", "name": "首批交付", "sales_order_id": order["id"], "harvest_document_id": 81, "quantity": 40, "delivered_at": "2026-08-18"})
    first = service.submit_delivery(maker, first["id"], {"expected_version": 1})
    service.verify_delivery(checker, first["id"], {"expected_version": 2, "evidence_attachment_ids": [10]})
    assert store.orders[order["id"]]["status"] == "partially_delivered"
    second = service.create_delivery(maker, {"code": "SD-2", "name": "剩余交付", "sales_order_id": order["id"], "harvest_document_id": 82, "quantity": 60, "delivered_at": "2026-08-19"})
    second = service.submit_delivery(maker, second["id"], {"expected_version": 1})
    service.verify_delivery(checker, second["id"], {"expected_version": 2, "evidence_attachment_ids": [11]})
    assert store.orders[order["id"]]["status"] == "fully_delivered"


def test_receipt_requires_method_voucher_and_separate_verifier_then_reverses() -> None:
    service = SalesService(SalesStore()); maker = actor(11, "finance.receivable.view", "finance.receipt.manage")
    checker = actor(12, "finance.receipt.verify"); editor = actor(13, "finance.receipt.manage", "finance.receipt.verify")
    receipt = service.create_receipt(maker, {"code": "RC-1", "name": "客户首款", "receivable_id": 31, "amount": 300, "received_at": "2026-08-20", "receipt_method": "bank_transfer"})
    receipt = service.submit_receipt(maker, receipt["id"], {"expected_version": 1})
    receipt = service.update_receipt(editor, receipt["id"], {"expected_version": 2, "note": "补录银行摘要"})
    with pytest.raises(DomainError, match="EVIDENCE_REQUIRED"):
        service.verify_receipt(checker, receipt["id"], {"expected_version": 3})
    receipt = service.verify_receipt(checker, receipt["id"], {"expected_version": 3, "evidence_attachment_ids": [12]})
    assert receipt["allowed_actions"] == ["view", "reverse"]
    for handler in (actor(11, "finance.receipt.verify"), editor):
        with pytest.raises(DomainError, match="SELF_APPROVAL_FORBIDDEN"):
            service.reverse_receipt(handler, receipt["id"], {"expected_version": 4, "reversal_reason": "经办人自行冲销", "evidence_attachment_ids": [13]})
    receipt = service.reverse_receipt(checker, receipt["id"], {"expected_version": 4, "reversal_reason": "银行退回", "evidence_attachment_ids": [13]})
    assert receipt["reversal_id"] == 9 and receipt["allowed_actions"] == ["view"]


def test_delivery_correction_requires_a_different_verified_harvest() -> None:
    store = SalesStore(); service = SalesService(store); maker = actor(7, "sales.manage")
    store.deliveries[1] = {
        "id": 1, "code": "SD-OLD", "name": "原交付", "sales_order_id": 1,
        "harvest_document_id": 81, "quantity": 40, "delivered_at": "2026-08-18",
        "status": "verified", "row_version": 3, "created_by": 7,
    }
    common = {"expected_version": 3, "code": "SD-NEW", "quantity": 35, "correction_reason": "客户复核"}

    with pytest.raises(DomainError, match="CORRECTION_HARVEST_REQUIRED"):
        service.correct_delivery(maker, 1, common)
    with pytest.raises(DomainError, match="CORRECTION_HARVEST_REQUIRED"):
        service.correct_delivery(maker, 1, {**common, "harvest_document_id": 81})


@pytest.mark.parametrize("invalid", ["nan", "inf", "-inf"])
def test_sales_amounts_reject_non_finite_numbers(invalid: str) -> None:
    with pytest.raises(DomainError, match="SALES_AMOUNT_INVALID"):
        SalesService.positive({"quantity": invalid}, "quantity")


def test_sales_migration_declares_append_only_financial_chain() -> None:
    sql = (ROOT / "database/migrations/013_sales_receivables.sql").read_text(encoding="utf-8")
    hardening = (ROOT / "database/migrations/014_sales_hardening.sql").read_text(encoding="utf-8")
    schema = (ROOT / "database/schema.sql").read_text(encoding="utf-8")
    for marker in ("CREATE TABLE sales_orders", "CREATE TABLE sales_deliveries", "CREATE TABLE sales_receivables", "CREATE TABLE sales_receipts", "CREATE TABLE sales_receipt_reversals", "sales_orders_no_formal_delete", "sales_deliveries_no_verified_update", "sales_receivables_no_delete", "sales_receipts_no_verified_update", "ON DELETE RESTRICT"):
        assert marker in sql
    for marker in ("harvest_root_id", "uq_sales_deliveries_harvest_root", "sales_orders_no_approved_business_update", "OLD.species", "OLD.unit", "OLD.total_amount"):
        assert marker in hardening
    assert "SOURCE database/migrations/013_sales_receivables.sql;" in schema
    assert "SOURCE database/migrations/014_sales_hardening.sql;" in schema


def test_sales_routes_are_registered_and_authorized() -> None:
    auth = FakeAuthStore()
    account = auth.add_user(phone="13800000909", login_name="sales-viewer", password="Correct9!", status="active")
    account["permissions"] = ["sales.view", "finance.receivable.view"]
    settings = Settings.from_env({
        "APP_ENV": "test", "FLASK_SECRET_KEY": "sales-test", "CSRF_SECRET_KEY": "sales-csrf",
        "MYSQL_HOST": "127.0.0.1", "MYSQL_DATABASE": "adp_test", "MYSQL_USER": "adp_test",
        "MYSQL_PASSWORD": "test", "SESSION_COOKIE_SECURE": "false",
    })
    client = create_app(settings, store=auth, sales_store=SalesStore()).test_client()
    token = client.get("/api/v1/auth/csrf").get_json()["data"]["csrf_token"]
    login = client.post("/api/v1/auth/login", json={"identifier": "sales-viewer", "password": "Correct9!"}, headers={"X-CSRF-Token": token})
    assert login.status_code == 200

    for path in ("orders", "deliveries", "receivables", "receipts"):
        assert client.get(f"/api/v1/sales/{path}").status_code == 200
    denied = client.post("/api/v1/sales/orders", json=order_payload(), headers={"X-CSRF-Token": token})
    assert denied.status_code == 403
    assert denied.get_json()["code"] == "FORBIDDEN"
